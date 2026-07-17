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
#   │                                                                          │
#   │  PICKING A MODEL — run with no MODEL= and you get a menu, or:            │
#   │    MODEL=llama8b   bash human_validation.slurm     (1 GPU  — default)    │
#   │    MODEL=qwen72b   bash human_validation.slurm     (2 GPUs REQUIRED)     │
#   │    MODEL=llama70b  bash human_validation.slurm     (2 GPUs REQUIRED)     │
#   │                                                                          │
#   │  ⚠ The 70B/72B models are ~140GB in bf16 and CANNOT fit on one 80GB      │
#   │    A100. For those you MUST allocate 2 GPUs:                             │
#   │      srun --gres=gpu:a100:2 --cpus-per-task=8 --mem=64G --time=04:00:00 \│
#   │           --pty bash human_validation.slurm                              │
#   │                                                                          │
#   │  Overrides (export before launching) if your setup differs:             │
#   │     CONDA_ENV=myenv  PROJECT_DIR=/path/to/code  VLLM_MODEL=/path/to/model│
#   │     TP_SIZE=4  (force a specific tensor-parallel size)                   │
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

# ── Model registry ───────────────────────────────────────────────────────────
# The original Qwen2.5-14B-Instruct was REMOVED from /home/support/llm (the share
# was reorganised on 7 Jul), which is why vLLM reported a confusing
# "Repo id must be in the form..." error — it could not find the local path and
# fell back to treating it as a HuggingFace repo name.
#
# Pick a model with:   MODEL=<key> bash human_validation.slurm
# or just run the script and choose from the menu.
#
#   key        path                                     bf16 weights   GPUs needed
#   ---------  ---------------------------------------  -------------  -----------
#   llama8b    Llama-3.1-8B-Instruct                     ~32 GB         1
#   qwen72b    Qwen2.5-72B-Instruct                      ~145 GB        2+ (TP)
#   llama70b   Llama-3.1-70B-Instruct                    ~141 GB        2+ (TP)
#
# NOTE: the 70B/72B models CANNOT fit on a single A100-80GB. They need tensor
# parallelism across 2+ GPUs, so allocate accordingly:
#     srun --gres=gpu:a100:2 ... --pty bash human_validation.slurm
declare -A MODEL_PATHS=(
    [llama8b]="/home/support/llm/Llama-3.1-8B-Instruct"
    [qwen72b]="/home/support/llm/Qwen2.5-72B-Instruct"
    [llama70b]="/home/support/llm/Llama-3.1-70B-Instruct"
)
declare -A MODEL_TP=(          # minimum tensor-parallel size (= GPUs required)
    [llama8b]=1
    [qwen72b]=2
    [llama70b]=2
)
declare -A MODEL_DESC=(
    [llama8b]="Llama-3.1-8B-Instruct   ~32GB   1 GPU   (fastest; fits one A100)"
    [qwen72b]="Qwen2.5-72B-Instruct   ~145GB   2 GPUs  (Qwen family, closest to the old 14B)"
    [llama70b]="Llama-3.1-70B-Instruct ~141GB   2 GPUs"
)

_pick_model() {
    echo ""
    echo "Available models:"
    local i=1
    for k in llama8b qwen72b llama70b; do
        echo "  $i) ${k}  —  ${MODEL_DESC[$k]}"
        i=$((i+1))
    done
    echo ""
    local choice
    read -r -p "Pick a model [1-3] (or press Enter for llama8b): " choice
    case "$choice" in
        1|"") MODEL_KEY="llama8b" ;;
        2)    MODEL_KEY="qwen72b" ;;
        3)    MODEL_KEY="llama70b" ;;
        llama8b|qwen72b|llama70b) MODEL_KEY="$choice" ;;
        *)    echo "[job][ERROR] invalid choice: $choice"; exit 1 ;;
    esac
}

# MODEL=<key> chooses non-interactively; VLLM_MODEL=<path> overrides entirely.
MODEL_KEY="${MODEL:-}"
if [ -n "${VLLM_MODEL:-}" ]; then
    MODEL_PATH="$VLLM_MODEL"
    TP_SIZE="${TP_SIZE:-1}"
else
    if [ -z "$MODEL_KEY" ]; then
        _pick_model
    fi
    if [ -z "${MODEL_PATHS[$MODEL_KEY]:-}" ]; then
        echo "[job][ERROR] unknown MODEL key: '$MODEL_KEY'"
        echo "             valid keys: llama8b qwen72b llama70b"
        exit 1
    fi
    MODEL_PATH="${MODEL_PATHS[$MODEL_KEY]}"
    TP_SIZE="${TP_SIZE:-${MODEL_TP[$MODEL_KEY]}}"
fi

# Fail LOUDLY if the model is missing/unreadable, instead of letting vLLM emit a
# misleading "Repo id must be in the form 'repo_name'..." error.
if [ ! -f "$MODEL_PATH/config.json" ]; then
    echo "[job][ERROR] model not found or not readable by ${USER:-$(whoami)}:"
    echo "             $MODEL_PATH"
    echo "             (no config.json there — vLLM would report a confusing"
    echo "              'Repo id must be in the form...' error for this)"
    echo "[job] models currently available:"
    ls -1 /home/support/llm/ 2>/dev/null | sed 's/^/               /'
    exit 1
fi

# vLLM loads weights from MODEL_PATH (a filesystem path) via --model, but the
# SERVED name must be a plain alias: newer huggingface_hub validates
# --served-model-name as a repo id and rejects a path with slashes
# ("Repo id must be in the form 'repo_name' or 'namespace/repo_name'").
# The client sends this same alias as its "model", so the two always agree.
SERVED_NAME="${SERVED_NAME:-${MODEL_KEY:-$(basename "$MODEL_PATH")}}"
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
export VLLM_MODEL_PATH="$MODEL_PATH"
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
pkill -u "${USER:-$(whoami)}" -f "vllm.entrypoints.openai.api_server" 2>/dev/null || true
sleep 2

echo "[job] node: $(hostname)"
echo "[job] CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
echo "[job] model: $MODEL_PATH"
echo "[job] tensor-parallel-size: $TP_SIZE"
echo "[job] python: $(which python)"

# ── Check enough GPUs were allocated for this model ──────────────────────────
# A 70B/72B model in bf16 needs ~140GB of weights and CANNOT fit on one 80GB
# A100 — it must be sharded across TP_SIZE GPUs. Fail now with a clear message
# rather than after a 2-minute load ending in CUDA OOM.
if [ -n "${CUDA_VISIBLE_DEVICES:-}" ]; then
    N_GPUS=$(echo "$CUDA_VISIBLE_DEVICES" | tr ',' '\n' | grep -c .)
else
    N_GPUS=$(nvidia-smi --list-gpus 2>/dev/null | grep -c . || echo 0)
fi
echo "[job] GPUs visible: $N_GPUS"
if [ "$N_GPUS" -lt "$TP_SIZE" ]; then
    echo "[job][ERROR] this model needs $TP_SIZE GPU(s) but only $N_GPUS is/are allocated."
    echo "             ~140GB of weights cannot fit on a single 80GB A100."
    echo "             Re-launch with more GPUs, e.g.:"
    echo "               srun --gres=gpu:a100:${TP_SIZE} --cpus-per-task=8 --mem=64G \\"
    echo "                    --time=04:00:00 --pty bash $(basename "$0") ${CLI_ARGS}"
    echo "             ...or pick a smaller model:  MODEL=llama8b bash $(basename "$0")"
    exit 1
fi

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
    --tensor-parallel-size "$TP_SIZE" \
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
echo "[job] waiting for vLLM /v1/models to respond..."
echo "[job]   (8B loads in ~1min; a 70B/72B sharded across GPUs can take 5-15min)"
for i in $(seq 1 120); do       # up to 120 * 10s = 20 minutes (70B needs it)
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
    if [ "$i" -eq 120 ]; then
        echo "[job][ERROR] vLLM server did not become healthy within 20 minutes."
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
