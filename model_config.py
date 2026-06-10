"""
model_config.py

Switch backend with ONE line — change BACKEND below.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPTION 1 — HuggingFace Inference API  (free, no GPU needed)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Get a free token: https://huggingface.co/settings/tokens
  Then: export HF_TOKEN=hf_...

    BACKEND  = "huggingface"
    HF_MODEL = "Qwen/Qwen2.5-14B-Instruct"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPTION 2 — Ollama  (local, Apple Silicon, no API key)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Install: https://ollama.com  then: ollama serve
  Pull:    ollama pull qwen2.5:32b

    BACKEND      = "ollama"
    OLLAMA_MODEL = "qwen2.5:32b"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPTION 3 — Anthropic API  (paid, highest quality)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    BACKEND = "anthropic"
    # export ANTHROPIC_API_KEY=sk-ant-...
"""

import os

# ═══════════════════════════════════════════════════════
#  CHANGE THIS ONE LINE TO SWITCH BACKEND
# ═══════════════════════════════════════════════════════
BACKEND = "ollama"
LMSTUDIO_MODEL = "qwen2.5-14b-instruct"  # must match name shown in LM Studio
LMSTUDIO_HOST  = "http://localhost:1234"        # "huggingface" | "ollama" | "anthropic"

OLLAMA_MODEL = "qwen2.5:7b-instruct"

OLLAMA_HOST     = "http://localhost:11434"

OLLAMA_CTX      = 8192

OLLAMA_TIMEOUT  = 180

# Role-specific Ollama models

OLLAMA_MODEL    = "qwen2.5:14b"
PERSONA_MODEL   = "qwen2.5:14b"
AGENT_MODEL     = "qwen2.5:14b"   # "huggingface" | "ollama" | "anthropic"

# ── HuggingFace ──────────────────────────────────────────────────────────────
# Recommended 13B–14B free-tier models (best → fallback):
#   "Qwen/Qwen2.5-14B-Instruct"              ← best instruction following
#   "mistralai/Mistral-Nemo-Instruct-2407"   ← 12B, strong, usually available
#   "microsoft/Phi-3-medium-4k-instruct"     ← 14B, fast reasoning
#   "Qwen/Qwen2.5-7B-Instruct"              ← lighter if 14B is slow
#   "meta-llama/Llama-3.1-8B-Instruct"     ← 8B fallback, always available
HF_MODEL       = "Qwen/Qwen2.5-7B-Instruct"
HF_TOKEN = ""  # Prefer: export HF_TOKEN=hf_...
HF_PROVIDER    = "together"  # Qwen/Qwen2.5-7B-Instruct is served via Together AI
HF_TIMEOUT     = 120         # seconds
HF_MAX_RETRIES = 3
HF_RETRY_DELAY = 25          # seconds to wait on cold start

# ── Ollama ───────────────────────────────────────────────────────────────────
# Apple Silicon presets:
#   96 GB → qwen2.5:72b    64 GB → qwen2.5:72b
#   32 GB → qwen2.5:32b    16 GB → qwen2.5:14b    8 GB → llama3.1:8b



# ── Role-specific model overrides (optional) ─────────────────────────────────
# Use a lighter model for the persona to speed up batch runs.
# None = use the primary model for that backend.
# HF example:    PERSONA_MODEL = "Qwen/Qwen2.5-7B-Instruct"
# Ollama example: PERSONA_MODEL = "llama3.1:8b"
AGENT_MODEL   = None
PERSONA_MODEL = None
SCORER_MODEL  = None


def get_config(role: str = "default") -> dict:
    """Resolve full config dict for a given role."""
    backend = os.environ.get("LLM_BACKEND", BACKEND)

    if backend == "huggingface":
        model = os.environ.get("HF_MODEL", HF_MODEL)
        overrides = {"agent": AGENT_MODEL, "persona": PERSONA_MODEL, "scorer": SCORER_MODEL}
        model = overrides.get(role) or model
        return {
            "backend": "huggingface",
            "model": model,
            "hf_token": os.environ.get("HF_TOKEN") or HF_TOKEN,
            "provider": os.environ.get("HF_PROVIDER", HF_PROVIDER),
            "timeout": HF_TIMEOUT,
            "hf_max_retries": HF_MAX_RETRIES,
            "hf_retry_delay": HF_RETRY_DELAY,
        }

    elif backend == "ollama":
        model = os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL)
        overrides = {"agent": AGENT_MODEL, "persona": PERSONA_MODEL, "scorer": SCORER_MODEL}
        model = overrides.get(role) or model
        return {
            "backend": "ollama",
            "model": model,
            "ollama_host": os.environ.get("OLLAMA_HOST", OLLAMA_HOST),
            "context_length": OLLAMA_CTX,
            "timeout": OLLAMA_TIMEOUT,
        }

    else:  # anthropic
        return {
            "backend": "anthropic",
            "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        }


def print_config():
    cfg = get_config()
    b = cfg["backend"]
    print("┌─ LLM Backend " + "─" * 42)
    print(f"│  Backend : {b}")
    print(f"│  Model   : {cfg['model']}")
    if b == "huggingface":
        tok = cfg.get("hf_token", "")
        print(f"│  HF Token: {tok[:8]}..." if tok else "│  HF Token: ⚠ NOT SET — export HF_TOKEN=hf_...")
        print(f"│  Timeout : {cfg['timeout']}s  |  Retries: {cfg['hf_max_retries']}")
    elif b == "ollama":
        print(f"│  Host    : {cfg['ollama_host']}")
        print(f"│  Context : {cfg['context_length']} tokens  |  Timeout: {cfg['timeout']}s")
    print("└" + "─" * 56)


if __name__ == "__main__":
    print_config()
