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
BACKEND = "vllm"   # "vllm" | "ollama" | "huggingface" | "anthropic"

# ── vLLM (cluster: A100-80GB, OpenAI-compatible server) ──────────────────────
# On the cluster the model weights live under /home/support/llm/. We serve them
# with vLLM, which exposes an OpenAI-compatible HTTP API on localhost. The Slurm
# job launches the server (see run_experiment.slurm) and this client talks to it.
#
# Qwen2.5-14B-Instruct in bf16 ≈ 30GB weights; on an 80GB A100 this leaves ample
# room for the KV cache. This is the closest match to the local qwen2.5:14b runs.
#
# To use a different served model, change VLLM_MODEL to the directory name under
# /home/support/llm/ (it is passed to vLLM as --model and used as the API "model").
VLLM_MODEL    = "/home/support/llm/Qwen2.5-14B-Instruct"
VLLM_HOST     = "http://localhost:8000"   # must match --port in the .slurm launch
VLLM_CTX      = 8192
VLLM_TIMEOUT  = 300                         # generous; first call after load is slow
VLLM_API_KEY  = "EMPTY"                     # vLLM ignores the key but the client sends one


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
OLLAMA_MODEL    = "qwen2.5:32b"
OLLAMA_HOST     = "http://localhost:11434"
OLLAMA_CTX      = 8192
OLLAMA_TIMEOUT  = 180

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

    if backend == "vllm":
        model = os.environ.get("VLLM_MODEL", VLLM_MODEL)
        overrides = {"agent": AGENT_MODEL, "persona": PERSONA_MODEL, "scorer": SCORER_MODEL}
        model = overrides.get(role) or model
        return {
            "backend": "vllm",
            "model": model,
            "vllm_host": os.environ.get("VLLM_HOST", VLLM_HOST),
            "context_length": VLLM_CTX,
            "timeout": VLLM_TIMEOUT,
            "api_key": os.environ.get("VLLM_API_KEY", VLLM_API_KEY),
        }

    elif backend == "huggingface":
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
    if b == "vllm":
        print(f"│  Host    : {cfg['vllm_host']}")
        print(f"│  Context : {cfg['context_length']} tokens  |  Timeout: {cfg['timeout']}s")
    elif b == "huggingface":
        tok = cfg.get("hf_token", "")
        print(f"│  HF Token: {tok[:8]}..." if tok else "│  HF Token: ⚠ NOT SET — export HF_TOKEN=hf_...")
        print(f"│  Timeout : {cfg['timeout']}s  |  Retries: {cfg['hf_max_retries']}")
    elif b == "ollama":
        print(f"│  Host    : {cfg['ollama_host']}")
        print(f"│  Context : {cfg['context_length']} tokens  |  Timeout: {cfg['timeout']}s")
    print("└" + "─" * 56)


if __name__ == "__main__":
    print_config()
