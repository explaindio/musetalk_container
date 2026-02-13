#!/usr/bin/env bash
set -euo pipefail
# Export environment variables to file for Vast.ai onstart scripts
cat > /app/.worker_env << EOF
export WORKER_MODE="${WORKER_MODE:-main}"
export WORKER_ID="${WORKER_ID:-unknown}"
export ORCHESTRATOR_BASE_URL="${ORCHESTRATOR_BASE_URL:-}"
export INTERNAL_API_KEY="${INTERNAL_API_KEY:-}"
export GPU_CLASS="${GPU_CLASS:-unknown}"
EOF

# Start the FastAPI worker app (MuseTalk processor) directly.
exec uvicorn worker_app.main:app --host 0.0.0.0 --port 8000
