#!/bin/bash
#SBATCH --job-name=s03_methodcheck
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --gres=gpu:a100:1
#SBATCH --time=1-00:00
# ─────────────────────────────────────────────────────────────────────────────
# MethodCheck experiment on the cluster.
#
# This job:
#   1. Launches a vLLM OpenAI-compatible server for Qwen2.5-14B-Instruct on the
#      allocated A100-80GB, in the background.
#   2. Waits for the server to become healthy.
#   3. Runs the RL experiment, which talks to the server over localhost.
#   4. Shuts the server down and exits.
#
# Submit with:   sbatch run_experiment.slurm
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ── Paths & config ───────────────────────────────────────────────────────────
PROJECT_DIR="/home/skrishna/method-mentor-main/method-mentor-new"
MODEL_PATH="/home/support/llm/Qwen2.5-14B-Instruct"
VLLM_PORT=8000
SCENARIO="S03"
RUNS=5
OUTLOG="output4_stages_included.log"

cd "$PROJECT_DIR"

# Tell the Python client which backend/host to use (overrides model_config.py).
export LLM_BACKEND="vllm"
export VLLM_MODEL="$MODEL_PATH"
export VLLM_HOST="http://localhost:${VLLM_PORT}"
export VLLM_API_KEY="EMPTY"

# ── Environment ──────────────────────────────────────────────────────────────
# IMPORTANT: review /home/support/llm/README first — the cluster may require a
# specific module load or a shared virtualenv to get vLLM. Adjust the two lines
# below to match. If vLLM is provided as a module:  module load vllm
# If you maintain your own venv:                    source ~/venvs/vllm/bin/activate
# As written, this assumes `vllm` and your project deps are already importable.
#
# Example (uncomment/edit as appropriate for this cluster):
# module purge
# module load cuda/12.4
# source "$HOME/venvs/methodcheck/bin/activate"

echo "[job] node: $(hostname)"
echo "[job] CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"
echo "[job] model: $MODEL_PATH"
nvidia-smi || true

# ── 1. Launch vLLM server in the background ──────────────────────────────────
# --served-model-name is set to the FULL PATH so it matches what the Python
# client sends as the "model" field (VLLM_MODEL). --max-model-len matches
# VLLM_CTX in model_config.py. --gpu-memory-utilization 0.90 leaves headroom.
echo "[job] starting vLLM server on port ${VLLM_PORT}..."
python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_PATH" \
    --served-model-name "$MODEL_PATH" \
    --port "$VLLM_PORT" \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.90 \
    --dtype bfloat16 \
    > vllm_server_${SLURM_JOB_ID}.log 2>&1 &
VLLM_PID=$!
echo "[job] vLLM server PID: $VLLM_PID"

# Ensure the server is killed when this job script exits, for any reason.
cleanup() {
    echo "[job] shutting down vLLM server (PID $VLLM_PID)..."
    kill "$VLLM_PID" 2>/dev/null || true
    wait "$VLLM_PID" 2>/dev/null || true
}
trap cleanup EXIT

# ── 2. Wait for the server to be healthy ─────────────────────────────────────
echo "[job] waiting for vLLM /v1/models to respond..."
for i in $(seq 1 60); do        # up to 60 * 10s = 10 minutes
    if curl -sf "http://localhost:${VLLM_PORT}/v1/models" \
            -H "Authorization: Bearer EMPTY" > /dev/null 2>&1; then
        echo "[job] vLLM server is healthy after $((i*10))s."
        break
    fi
    if ! kill -0 "$VLLM_PID" 2>/dev/null; then
        echo "[job][ERROR] vLLM process died during startup. See vllm_server_${SLURM_JOB_ID}.log"
        exit 1
    fi
    sleep 10
    if [ "$i" -eq 60 ]; then
        echo "[job][ERROR] vLLM server did not become healthy within 10 minutes."
        exit 1
    fi
done

# ── 3. Run the experiment ────────────────────────────────────────────────────
echo "[job] running experiment: scenario=${SCENARIO} runs=${RUNS}"
python run_experiment.py --scenario "$SCENARIO" --runs "$RUNS" > "$OUTLOG" 2>&1
EXP_STATUS=$?
echo "[job] experiment finished with status ${EXP_STATUS}. Log: ${OUTLOG}"

# 4. cleanup() runs automatically via the EXIT trap.
exit $EXP_STATUS
