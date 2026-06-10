"""
model_config.py — LLM backend configuration.

CHANGE BACKEND HERE (one line):
    BACKEND = "huggingface"   # free, no GPU, needs HF_TOKEN
    BACKEND = "ollama"        # local, Apple Silicon, no API key
    BACKEND = "anthropic"     # paid, highest quality

IMPORTANT: HF_PROVIDER has been removed.
Setting a third-party provider (together, fireworks, etc.) routes to PAID
endpoints and causes 402 Payment Required. The api_client.py forces
base_url to the free api-inference.huggingface.co endpoint regardless.
"""

import os

# ═══════════════════════════════════════════
BACKEND = "huggingface"
# ═══════════════════════════════════════════

# ── HuggingFace ──────────────────────────────────────────────────────────────
# Free-tier 7B–14B models (best → fallback):
#   "Qwen/Qwen2.5-14B-Instruct"              ← best instruction following
#   "Qwen/Qwen2.5-7B-Instruct"              ← lighter, faster
#   "mistralai/Mistral-Nemo-Instruct-2407"   ← 12B, reliable free tier
#   "microsoft/Phi-3-medium-4k-instruct"     ← 14B, good reasoning
#   "meta-llama/Llama-3.1-8B-Instruct"     ← 8B fallback (needs license accept)
HF_MODEL       = "Qwen/Qwen2.5-7B-Instruct"
HF_TOKEN       = ""           # prefer: export HF_TOKEN=hf_...
HF_TIMEOUT     = 120
HF_MAX_RETRIES = 3
HF_RETRY_DELAY = 25

# NOTE: HF_PROVIDER deliberately removed — it caused 402 errors.
# The free endpoint is forced in api_client.py via base_url.

# ── Ollama ───────────────────────────────────────────────────────────────────
OLLAMA_MODEL   = "qwen2.5:32b"
OLLAMA_HOST    = "http://localhost:11434"
OLLAMA_CTX     = 8192
OLLAMA_TIMEOUT = 180

# ── Role-specific overrides (optional) ───────────────────────────────────────
AGENT_MODEL   = None
PERSONA_MODEL = None
SCORER_MODEL  = None


def get_config(role: str = "default") -> dict:
    backend = os.environ.get("LLM_BACKEND", BACKEND)

    if backend == "huggingface":
        model = os.environ.get("HF_MODEL", HF_MODEL)
        overrides = {"agent": AGENT_MODEL, "persona": PERSONA_MODEL, "scorer": SCORER_MODEL}
        model = overrides.get(role) or model
        return {
            "backend":        "huggingface",
            "model":          model,
            "hf_token":       os.environ.get("HF_TOKEN") or HF_TOKEN,
            "timeout":        HF_TIMEOUT,
            "hf_max_retries": HF_MAX_RETRIES,
            "hf_retry_delay": HF_RETRY_DELAY,
        }

    elif backend == "ollama":
        model = os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL)
        overrides = {"agent": AGENT_MODEL, "persona": PERSONA_MODEL, "scorer": SCORER_MODEL}
        model = overrides.get(role) or model
        return {
            "backend":        "ollama",
            "model":          model,
            "ollama_host":    os.environ.get("OLLAMA_HOST", OLLAMA_HOST),
            "context_length": OLLAMA_CTX,
            "timeout":        OLLAMA_TIMEOUT,
        }

    else:  # anthropic
        return {
            "backend": "anthropic",
            "model":   os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
        }


def print_config():
    cfg = get_config()
    b   = cfg["backend"]
    print("┌─ LLM Backend " + "─" * 42)
    print(f"│  Backend : {b}")
    print(f"│  Model   : {cfg['model']}")
    if b == "huggingface":
        tok = cfg.get("hf_token", "")
        print(f"│  HF Token: {tok[:8]}..." if tok else
              "│  HF Token: ⚠ NOT SET — export HF_TOKEN=hf_...")
        print(f"│  Endpoint: api-inference.huggingface.co (FREE)")
        print(f"│  Timeout : {cfg['timeout']}s  |  Retries: {cfg['hf_max_retries']}")
    elif b == "ollama":
        print(f"│  Host    : {cfg['ollama_host']}")
        print(f"│  Context : {cfg['context_length']} tokens  |  Timeout: {cfg['timeout']}s")
    print("└" + "─" * 56)


if __name__ == "__main__":
    print_config()
