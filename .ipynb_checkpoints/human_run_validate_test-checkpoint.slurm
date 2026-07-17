#!/bin/bash
#SBATCH --job-name=mc_human_val
#SBATCH --output=human_val_%j.out
#SBATCH --error=human_val_%j.err
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --gres=gpu:a100:1
#SBATCH --time=04:00:00
# ─────────────────────────────────────────────────────────────────────────────
# MethodCheck — INTERACTIVE human-validation launcher (vLLM backend).
#
# human_validation.py is INTERACTIVE: you type the student's replies at the
# prompt. A normal batch `sbatch` job has NO terminal attached, so it cannot be
# interactive. This script must therefore be run inside an INTERACTIVE
# allocation so your keyboard is connected to the program.
#
#   ┌─────────────────────────────────────────────────────────────────────────┐
#   │  HOW TO RUN (interactive — REQUIRED so you can type):                    │
#   │                                                                          │
#   │    cd <your project dir, where this script and the .py files live>       │
#   │    salloc --gres=gpu:a100:1 --cpus-per-task=8 --mem=64G --time=04:00:00  │
#   │    # wait for the allocation; your prompt moves to a compute node        │
#   │    bash human_validation.slurm                                           │
#   │                                                                          │
#   │  OR in a single command:                                                 │
#   │                                                                          │
#   │    srun --gres=gpu:a100:1 --cpus-per-task=8 --mem=64G --time=04:00:00 \  │
#   │         --pty bash human_validation.slurm                                │
#   │                                                                          │
#   │  Works for ANY user: conda is auto-detected (anaconda3 / miniconda3 /    │
#   │  on PATH) and the project dir defaults to where this script lives.       │
#   │  Overrides (export before launching) if your setup differs:             │
#   │     CONDA_ENV=myenv  PROJECT_DIR=/path/to/code  VLLM_MODEL=/path/to/model│
#   └─────────────────────────────────────────────────────────────────────────┘
#
#   The #SBATCH lines above let you ALSO `sbatch` this file, but a batch run has
#   no stdin — only do that if you have wired a transcript into stdin. For normal
#   hand-driven validation, use salloc / srun --pty as shown above.
#
# This script:
#   1. Launches a vLLM OpenAI-compatible server for Qwen2.5-14B on the allocated
#      A100, in the background, on a runtime-chosen FREE port.
#   2. Waits for the server to become healthy.
#   3. Exports the backend env vars so human_validation.py uses vLLM (NOT ollama).
#   4. Runs human_validation.py INTERACTIVELY (stdin/stdout stay on your terminal).
#   5. Shuts the vLLM server down on exit.
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Paths & config ───────────────────────────────────────────────────────────
# PROJECT_DIR defaults to the directory this script lives in, so it works for any
# user from any checkout location without editing. Override by exporting
# PROJECT_DIR before launching if your script and code live in different places.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$SCRIPT_DIR}"
MODEL_PATH="${VLLM_MODEL:-/home/support/llm/Qwen2.5-14B-Instruct}"
# vLLM loads weights from MODEL_PATH (a filesystem path) via --model, but the
# SERVED name must be a plain alias: newer huggingface_hub validates
# --served-model-name as a repo id and rejects a path with slashes
# ("Repo id must be in the form 'repo_name' or 'namespace/repo_name'").
# The client sends this same alias as its "model", so the two always agree.
SERVED_NAME="${SERVED_NAME:-qwen}"
# Conda env name to activate (override with CONDA_ENV=... if yours differs).
CONDA_ENV="${CONDA_ENV:-prac}"
# Pass extra args straight through to human_validation.py, e.g.:
#   bash human_validation.slurm --scenario S01
#   bash human_validation.slurm --freeform --name "Priya"
#   bash human_validation.slurm --no-db
CLI_ARGS="${@:-}"

cd "$PROJECT_DIR"

# Tell the Python client to use vLLM (overrides BACKEND="ollama" in model_config.py).
# VLLM_MODEL here is what the CLIENT sends as its "model" field — it must match
# the server's --served-model-name (the alias), NOT the load path.
export LLM_BACKEND="vllm"
export VLLM_MODEL="$SERVED_NAME"
export VLLM_API_KEY="EMPTY"

# ── Environment ──────────────────────────────────────────────────────────────
# Locate conda for ANY user: try the standard install dirs, then a conda already
# on PATH. This works whether you use anaconda3, miniconda3, or miniforge3.
_conda_sh=""
for _base in "$HOME/anaconda3" "$HOME/miniconda3" "$HOME/miniforge3" \
             "$HOME/mambaforge" "/opt/anaconda3" "/opt/miniconda3"; do
    if [ -f "$_base/etc/profile.d/conda.sh" ]; then
        _conda_sh="$_base/etc/profile.d/conda.sh"
        break
    fi
done
if [ -z "$_conda_sh" ] && command -v conda >/dev/null 2>&1; then
    # conda is already on PATH — derive its profile script from `conda info --base`
    _base="$(conda info --base 2>/dev/null)"
    [ -f "$_base/etc/profile.d/conda.sh" ] && _conda_sh="$_base/etc/profile.d/conda.sh"
fi
if [ -z "$_conda_sh" ]; then
    echo "[job][ERROR] could not locate conda.sh. Set it manually, e.g.:"
    echo "             source /path/to/conda/etc/profile.d/conda.sh"
    exit 1
fi
echo "[job] using conda: $_conda_sh"
source "$_conda_sh"
conda activate "$CONDA_ENV"
echo "[job] active env: $CONDA_DEFAULT_ENV"

# Clear any stale vLLM server this user left on this node from a previous job.
pkill -u "$USER" -f "vllm.entrypoints.openai.api_server" 2>/dev/null || true
sleep 2

echo "[job] node: $(hostname)"
echo "[job] CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
echo "[job] model: $MODEL_PATH"
echo "[job] python: $(which python)"

# ── Find a genuinely free port at runtime ────────────────────────────────────
VLLM_PORT=$(python - <<'PYPORT'
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PYPORT
)
export VLLM_HOST="http://localhost:${VLLM_PORT}"
echo "[job] selected free port: $VLLM_PORT"
echo "[job] VLLM_HOST: $VLLM_HOST"

# ── 1. Launch vLLM server in the background ──────────────────────────────────
JOBTAG="${SLURM_JOB_ID:-interactive_$$}"
echo "[job] starting vLLM server on port ${VLLM_PORT}..."
python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_PATH" \
    --served-model-name "$SERVED_NAME" \
    --port "$VLLM_PORT" \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.90 \
    --dtype bfloat16 \
    > "vllm_server_${JOBTAG}.log" 2>&1 &
VLLM_PID=$!
echo "[job] vLLM server PID: $VLLM_PID  (log: vllm_server_${JOBTAG}.log)"

# Ensure the server is killed when this script exits, for any reason.
cleanup() {
    echo ""
    echo "[job] shutting down vLLM server (PID $VLLM_PID)..."
    kill "$VLLM_PID" 2>/dev/null || true
    wait "$VLLM_PID" 2>/dev/null || true
}
trap cleanup EXIT

# ── 2. Wait for the server to be healthy ─────────────────────────────────────
echo "[job] waiting for vLLM /v1/models to respond (model load ~40-90s)..."
for i in $(seq 1 60); do        # up to 60 * 10s = 10 minutes
    if curl -sf "http://localhost:${VLLM_PORT}/v1/models" \
            -H "Authorization: Bearer EMPTY" > /dev/null 2>&1; then
        echo "[job] vLLM server is healthy after $((i*10))s."
        break
    fi
    if ! kill -0 "$VLLM_PID" 2>/dev/null; then
        echo "[job][ERROR] vLLM process died during startup. See vllm_server_${JOBTAG}.log"
        exit 1
    fi
    sleep 10
    if [ "$i" -eq 60 ]; then
        echo "[job][ERROR] vLLM server did not become healthy within 10 minutes."
        exit 1
    fi
done

# ── 3. Run the INTERACTIVE human-validation CLI ──────────────────────────────
# NOTE: NO output redirection here — stdin/stdout stay attached to your terminal
# so you can type the student's replies and read the agent's responses live.
echo "[job] launching human_validation.py (interactive)..."
echo ""
python human_validation.py $CLI_ARGS

# 4. cleanup() runs automatically via the EXIT trap when you exit the CLI.
echo "[job] human_validation.py exited."
