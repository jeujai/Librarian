#!/usr/bin/env bash
# Run the model-server natively on the macOS host (Apple Silicon / MPS).
#
# Why: the model-server Docker container runs in the Colima Linux VM, which
# cannot see Apple Metal. Running it here lets the bi-encoder (bge-base-en-v1.5)
# use the MPS backend for large batched embeddings (ingestion + query embedding).
#
# The cross-encoder (bge-reranker-base) runs on MPS by default now that the
# rerank window is ~50 chunks per query. If MPS dispatch overhead makes it
# slower than CPU for small batches, set CROSS_ENCODER_DEVICE=cpu.
#
# The app container reaches this process via http://host.docker.internal:8001
# (Colima already maps host.docker.internal to the host; no extra_hosts needed).
#
# Usage:
#   scripts/start-model-server-native.sh
#   VENV=/path/to/venv scripts/start-model-server-native.sh
#   scripts/start-model-server-native.sh --help

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV="${VENV:-${PROJECT_ROOT}/venv}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8001}"

# Model configuration (kept in sync with docker-compose.yml model-server service).
export EMBEDDING_MODEL="${EMBEDDING_MODEL:-BAAI/bge-base-en-v1.5}"
export NLP_MODEL="${NLP_MODEL:-en_core_web_md}"
export CROSS_ENCODER_MODEL="${CROSS_ENCODER_MODEL:-BAAI/bge-reranker-base}"
export EMBEDDING_DEVICE="${EMBEDDING_DEVICE:-mps}"
export CROSS_ENCODER_DEVICE="${CROSS_ENCODER_DEVICE:-mps}"
export PRELOAD_MODELS="${PRELOAD_MODELS:-true}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

# --- Helpers ---------------------------------------------------------------

usage() {
    cat <<EOF
Start the model-server natively on the host (MPS-enabled embedding).

Environment overrides:
  VENV                   Path to the virtualenv (default: <repo>/venv)
  HOST                   Bind address (default: 0.0.0.0)
  PORT                   Port (default: 8001)
  EMBEDDING_DEVICE       mps|cpu (default: mps)
  CROSS_ENCODER_DEVICE   mps|cpu (default: cpu)

The app container must point MODEL_SERVER_URL at
http://host.docker.internal:8001 to use this process.
EOF
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

# --- Preflight -------------------------------------------------------------

if [[ ! -x "${VENV}/bin/python" ]]; then
    echo "error: venv not found at ${VENV}/bin/python" >&2
    echo "       create one with: python3.12 -m venv ${VENV}" >&2
    exit 1
fi

if lsof -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "error: port ${PORT} is already in use" >&2
    echo "       (the Docker model-server maps 8001:8001 — stop it first with:" >&2
    echo "        docker compose stop model-server)" >&2
    lsof -iTCP:"${PORT}" -sTCP:LISTEN >&2
    exit 1
fi

# Confirm MPS is actually available before advertising it.
if [[ "${EMBEDDING_DEVICE}" == "mps" ]]; then
    if ! "${VENV}/bin/python" -c "import torch; assert torch.backends.mps.is_available()" 2>/dev/null; then
        echo "warning: MPS not available, falling back to cpu for embedding" >&2
        export EMBEDDING_DEVICE=cpu
    fi
fi

# --- Run -------------------------------------------------------------------

cd "${PROJECT_ROOT}"
echo "Starting native model-server:"
echo "  venv:        ${VENV}"
echo "  bind:        ${HOST}:${PORT}"
echo "  embedding:   ${EMBEDDING_MODEL} (${EMBEDDING_DEVICE})"
echo "  cross-enc:   ${CROSS_ENCODER_MODEL} (${CROSS_ENCODER_DEVICE})"
echo "  nlp:         ${NLP_MODEL}"

exec "${VENV}/bin/python" -m uvicorn \
    src.model_server.main:app \
    --host "${HOST}" \
    --port "${PORT}" \
    --log-level "$(echo "${LOG_LEVEL}" | tr '[:upper:]' '[:lower:]')"
