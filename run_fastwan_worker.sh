#!/usr/bin/env bash
set -euo pipefail

# Check WORKER_MODE environment variable
WORKER_MODE="${WORKER_MODE:-queue}"

if [ "$WORKER_MODE" = "buffer" ]; then
    echo "Starting FastWan worker in BUFFER mode..."
    # Buffer mode: Run the Python main() directly, which handles heartbeat + job claim
    exec python -m worker_app_fastwan.main
else
    echo "Starting FastWan worker in QUEUE mode (Salad)..."
    
    # Start the Salad HTTP Job Queue Worker in the background.
    # It connects to Salad's queue and sends requests to our local FastAPI app at port 8000.
    /usr/local/bin/salad-http-job-queue-worker &
    WORKER_PID=$!
    
    # Start the FastAPI worker app (FastWan processor).
    exec uvicorn worker_app_fastwan.main:app --host 0.0.0.0 --port 8000 &
    API_PID=$!
    
    # Wait for either process to exit.
    wait -n "$WORKER_PID" "$API_PID"
    
    # Exit with the status of the first process that exited.
    exit $?
fi
