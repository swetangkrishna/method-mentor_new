"""
retrieval.py — RAG retrieval layer for MethodCheck (Option A).

Design principles:
  - GRACEFUL DEGRADATION: if sentence-transformers / faiss are not installed, or
    the index has not been built, every public function returns "no results" and
    the experiment runs EXACTLY as it does without RAG. RAG never blocks a run.
  - BUILD ONCE, LOAD MANY: the FAISS index + chunk store are built by
    build_index.py and cached to disk; experiments only LOAD them (fast).
  - RETRIEVE ONLY WHEN NEEDED: should_retrieve() encodes the trigger policy so we
    do not query the index on rapport/onboarding turns.
  - PER-EPISODE CACHE: identical queries within one episode reuse prior results.

Public API:
    rag_available() -> bool
    should_retrieve(stage, student_text) -> bool
    retrieve(query, k=None, episode_cache=None) -> list[dict]   # dicts: text, source, score
    new_episode_cache() -> dict
"""

import json
import os
import re
from typing import List, Dict, Optional

import rag_config as C

# ── Optional dependencies: import defensively ─────────────────────────────────
_IMPORT_ERROR = None
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    import faiss
    _LIBS_OK = True
except Exception as e:          # ImportError or any load-time failure
    _LIBS_OK = False
    _IMPORT_ERROR = str(e)

# Lazily-loaded singletons (model + index are loaded once per process).
_MODEL = None
_INDEX = None
_CHUNKS: Optional[List[Dict]] = None     # list of {"text":..., "source":...}
_LOAD_ERROR = None


def rag_available() -> bool:
    """True only if the libraries are importable AND a built index exists on disk."""
    if not _LIBS_OK:
        return False
    return (os.path.exists(C.RAG_INDEX_FILE)
            and os.path.exists(C.RAG_CHUNKS_FILE))


def _ensure_loaded() -> bool:
    """Load model + index + chunks on first use. Returns False on any failure."""
    global _MODEL, _INDEX, _CHUNKS, _LOAD_ERROR
    if not _LIBS_OK:
        return False
    if _INDEX is not None and _MODEL is not None and _CHUNKS is not None:
        return True
    try:
        if _MODEL is None:
            _MODEL = SentenceTransformer(C.RAG_EMBED_MODEL)
        if _INDEX is None:
            if not os.path.exists(C.RAG_INDEX_FILE):
                _LOAD_ERROR = f"index file missing: {C.RAG_INDEX_FILE}"
                return False
            _INDEX = faiss.read_index(C.RAG_INDEX_FILE)
        if _CHUNKS is None:
            chunks = []
            with open(C.RAG_CHUNKS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        chunks.append(json.loads(line))
            _CHUNKS = chunks
        return True
    except Exception as e:
        _LOAD_ERROR = str(e)
        return False


# ── Retrieval trigger policy ──────────────────────────────────────────────────

_TRIGGER_RE = re.compile(
    "|".join(re.escape(t) for t in C.RAG_TRIGGER_TERMS), re.IGNORECASE
)

def should_retrieve(stage: int, student_text: str) -> bool:
    """
    Decide whether THIS turn warrants a retrieval (retrieve-only-when-needed).
      - Always retrieve in the method-heavy stages (RAG_ALWAYS_STAGES).
      - Otherwise retrieve only if the student's last message contains a
        substantive methods term.
    Returns False fast if RAG is unavailable, so callers need no extra guard.
    """
    if not rag_available():
        return False
    if stage in C.RAG_ALWAYS_STAGES:
        return True
    if student_text and _TRIGGER_RE.search(student_text):
        return True
    return False


# ── Per-episode query cache ───────────────────────────────────────────────────

def new_episode_cache() -> dict:
    """Fresh cache for one episode: maps normalised query -> results list."""
    return {}

def _norm_query(q: str) -> str:
    return re.sub(r"\s+", " ", (q or "").strip().lower())


# ── Core retrieval ────────────────────────────────────────────────────────────

def retrieve(query: str, k: Optional[int] = None,
             episode_cache: Optional[dict] = None) -> List[Dict]:
    """
    Return up to k chunks most relevant to `query`, each as:
        {"text": str, "source": str, "score": float}   # score = L2 distance
    Returns [] if RAG is unavailable, the query is empty, or nothing passes the
    distance threshold. Never raises — failures degrade to [].
    """
    if not query or not rag_available():
        return []
    k = k or C.RAG_TOP_K

    # Per-episode cache hit?
    if episode_cache is not None:
        key = _norm_query(query)
        if key in episode_cache:
            return episode_cache[key]

    if not _ensure_loaded():
        return []

    try:
        q_emb = _MODEL.encode([query], convert_to_numpy=True)
        distances, indices = _INDEX.search(q_emb, k)
        out: List[Dict] = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(_CHUNKS):
                continue
            if C.RAG_MAX_DISTANCE is not None and float(dist) > C.RAG_MAX_DISTANCE:
                continue
            ch = _CHUNKS[idx]
            out.append({
                "text":   ch.get("text", ""),
                "source": ch.get("source", "unknown"),
                "score":  round(float(dist), 4),
            })
    except Exception:
        return []

    if episode_cache is not None:
        episode_cache[_norm_query(query)] = out
    return out


def format_for_prompt(chunks: List[Dict], max_chars: int = 1200) -> str:
    """
    Render retrieved chunks as a reference block for the agent's system prompt,
    under the strict Option-A framing: background to inform QUESTIONS, never to
    deliver answers. Returns "" if there are no chunks.
    """
    if not chunks:
        return ""
    lines = [
        "## BACKGROUND FROM THE METHODS LITERATURE (for YOUR reference only)",
        "The following excerpts are retrieved from research-methods sources. Use "
        "them ONLY to make your scaffolding QUESTIONS better grounded. Do NOT quote "
        "them, do NOT lecture, and do NOT hand these facts to the student as answers. "
        "You are still scaffolding — the student must reach conclusions themselves.",
    ]
    used = 0
    for i, ch in enumerate(chunks, 1):
        snippet = ch["text"].strip().replace("\n", " ")
        if used + len(snippet) > max_chars:
            snippet = snippet[: max(0, max_chars - used)]
        if not snippet:
            break
        src = os.path.basename(ch.get("source", "")) or "source"
        lines.append(f"  [{i}] ({src}) {snippet}")
        used += len(snippet)
        if used >= max_chars:
            break
    return "\n".join(lines)


def status() -> Dict:
    """Diagnostic snapshot for logging at experiment start."""
    return {
        "libs_ok": _LIBS_OK,
        "import_error": _IMPORT_ERROR,
        "index_present": os.path.exists(C.RAG_INDEX_FILE),
        "chunks_present": os.path.exists(C.RAG_CHUNKS_FILE),
        "available": rag_available(),
        "embed_model": C.RAG_EMBED_MODEL,
        "top_k": C.RAG_TOP_K,
    }