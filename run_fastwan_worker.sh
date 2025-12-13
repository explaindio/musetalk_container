#!/usr/bin/env bash
set -euo pipefail

# Start the Salad HTTP Job Queue Worker in the background.
# It connects to Salad's queue and sends requests to our local FastAPI app at port 8000.
/usr/local/bin/salad-http-job-queue-worker &
WORKER_PID=$!

# Start the FastAPI worker app (FastWan processor).
# Using --host 0.0.0.0 to accept connections from the queue worker.
# Using --timeout-keep-alive 300 because generation can take some time (though <60s usually).
exec uvicorn worker_app_fastwan.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

# Wait for either process to exit.
wait -n "$WORKER_PID" "$API_PID"

# Exit with the status of the first process that exited.
exit $?
