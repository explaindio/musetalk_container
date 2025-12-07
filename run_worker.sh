#!/usr/bin/env bash
set -euo pipefail

# Start the Salad HTTP Job Queue Worker in the background.
/usr/local/bin/salad-http-job-queue-worker &
WORKER_PID=$!

# Start the FastAPI worker app (MuseTalk processor).
uvicorn worker_app.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Wait for either process to exit.
wait -n "$WORKER_PID" "$API_PID"

# Exit with the status of the first process that exited.
exit $?

