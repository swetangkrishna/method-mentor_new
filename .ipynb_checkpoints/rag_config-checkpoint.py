"""
rag_config.py — Configuration for the RAG retrieval layer (Option A: retrieval
informs the agent's scaffolding; it is NEVER used to hand the student answers).

Everything here is read by retrieval.py and build_index.py. Paths default to the
cluster layout but can be overridden with environment variables.
"""

import os

# ── Source documents ──────────────────────────────────────────────────────────
# Directory containing the research-methods PDFs (the ~30 textbooks).
RAG_PDF_DIR = os.environ.get(
    "RAG_PDF_DIR",
    "/home/skrishna/method-mentor-main/method-mentor-new/method-mentor_new/RAG",
)

# Sample webpages to test the web side of retrieval. Replace with the real
# approved sources later; these are placeholders for a first end-to-end test.
RAG_SAMPLE_URLS = [
    "https://www.scribbr.com/category/methodology/",
    "https://methods.sagepub.com/",
]
# Set to True to also ingest RAG_SAMPLE_URLS when building the index. Off by
# default so the first build is just the local PDFs (fast, offline-safe).
RAG_INCLUDE_URLS = os.environ.get("RAG_INCLUDE_URLS", "0") == "1"

# ── Index cache ───────────────────────────────────────────────────────────────
# The built FAISS index + chunk store are cached here so the index is built ONCE
# (by build_index.py) and merely loaded by every experiment run.
RAG_CACHE_DIR = os.environ.get(
    "RAG_CACHE_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "rag_cache"),
)
RAG_INDEX_FILE  = os.path.join(RAG_CACHE_DIR, "faiss.index")
RAG_CHUNKS_FILE = os.path.join(RAG_CACHE_DIR, "chunks.jsonl")  # text + source per chunk
RAG_META_FILE   = os.path.join(RAG_CACHE_DIR, "meta.json")     # build info / model name

# ── Chunking & embedding ──────────────────────────────────────────────────────
RAG_CHUNK_SIZE     = 500
RAG_CHUNK_OVERLAP  = 50
RAG_EMBED_MODEL    = os.environ.get("RAG_EMBED_MODEL", "all-MiniLM-L6-v2")
RAG_TOP_K          = int(os.environ.get("RAG_TOP_K", "4"))
# Chunks with an L2 distance above this are treated as irrelevant and dropped.
# (Lower = stricter. None = keep all top-k regardless of distance.)
RAG_MAX_DISTANCE   = float(os.environ.get("RAG_MAX_DISTANCE", "1.5"))

# ── Retrieval trigger policy (retrieve only when required) ───────────────────
# Stages where retrieval ALWAYS runs (method grounding genuinely needed).
RAG_ALWAYS_STAGES = {4, 5}
# In other stages, retrieve only if the student's last message contains one of
# these substantive methods terms — otherwise skip (rapport/onboarding turns).
RAG_TRIGGER_TERMS = [
    "validity", "reliability", "rigour", "rigor", "generalis", "generaliz",
    "sampling", "sample size", "thematic", "coding", "triangulat",
    "interview", "survey", "questionnaire", "observation", "focus group",
    "mixed method", "qualitative", "quantitative", "ethic", "consent",
    "epistemolog", "ontolog", "positivis", "interpretivis", "constructivis",
    # Stage 3 required-parameter vocabulary (research_aim, required_data_type,
    # evidence_orientation) so those questions can be grounded by retrieval.
    "pragmatic", "pragmatism", "exploratory", "explanatory", "evaluative",
    "measurable", "observable", "convincing evidence",
    "case study", "ethnograph", "grounded theory", "phenomenolog",
    "bias", "saturation", "transferab", "credibility", "trustworth",
    "regression", "statistic", "variable", "correlation", "significance",
    "data analysis", "research design", "secondary data", "dataset",
]