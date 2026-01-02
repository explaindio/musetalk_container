#!/bin/bash
# Remove strict node so we don't crash silently
# set -euo pipefail

# Force output to stdout/stderr immediately
export PYTHONUNBUFFERED=1

echo "================================================================"
echo "   FASTWAN WORKER CONTAINER STARTING"
echo "   Time: $(date)"
echo "================================================================"

# Trap errors
trap 'echo "ERROR: Script failed at line $LINENO"' ERR

echo "debug: checking environment..."
echo "PATH: $PATH"
echo "PWD: $(pwd)"

# ============================================================================
# SHARED MEMORY CHECK
# ============================================================================
echo "debug: checking shared memory..."
if [ -d "/dev/shm" ]; then
    SHM_SIZE=$(df -h /dev/shm | tail -1 | awk '{print $2}')
    echo "Shared Memory (/dev/shm) size reported: $SHM_SIZE"
else
    echo "WARNING: /dev/shm does not exist or is not a directory."
fi

# ============================================================================
# ENVIRONMENT SETUP
# ============================================================================
export PYTHONPATH="/workspace:${PYTHONPATH:-}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
# Force spawn method diagnostics
export PYTHONFAULTHANDLER=1
export WORKER_MODE="${WORKER_MODE:-queue}"

echo "debug: environment variables set."
echo "WORKER_MODE: $WORKER_MODE"

# ============================================================================
# PYTORCH & GPU CHECK
# ============================================================================
echo "debug: run python torch check..."
python3 -u -c "
import sys
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    try:
        print(f'Arch list: {torch.cuda.get_arch_list()}')
    except:
        pass
else:
    print('WARNING: CUDA is NOT available')
" || echo "WARNING: Python torch check failed!"

# ============================================================================
# MULTIPROCESSING TEST
# ============================================================================
echo "debug: testing multiprocessing spawn..."
python3 -u -c "
import multiprocessing as mp
import sys
import os

print(f'CPU count: {mp.cpu_count()}')

try:
    mp.set_start_method('spawn', force=True)
    print('Spawn method set.')
except Exception as e:
    print(f'Checking start method: {e}')

def worker(x):
    return x * 2

if __name__ == '__main__':
    try:
        ctx = mp.get_context('spawn')
        with ctx.Pool(1) as p:
            result = p.map(worker, [1, 2, 3])
        print(f'Multiprocessing OK: {result}')
    except Exception as e:
        print(f'Multiprocessing FAILED: {e}')
        # Do not exit, just warn so we can see logs
        print('WARNING: This likely means --ipc=host is missing!')
" || echo "WARNING: Multiprocessing test crashed!"

echo "==============================="
echo "   STARTING APPLICATION"
echo "==============================="

# ============================================================================
# START WORKER
# ============================================================================
if [ "$WORKER_MODE" = "buffer" ]; then
    echo "Starting FastWan worker in BUFFER mode..."
    exec python3 -u -m worker_app_fastwan.main
else
    echo "Starting FastWan worker in QUEUE mode (Salad)..."
    
    # Check if salad worker binary exists
    if [ -f "/usr/local/bin/salad-http-job-queue-worker" ]; then
        echo "Starting Salad Job Queue Worker..."
        /usr/local/bin/salad-http-job-queue-worker &
        WORKER_PID=$!
    else
        echo "ERROR: Salad worker binary not found at /usr/local/bin/salad-http-job-queue-worker"
        # Don't exit, try to run app anyway so logs are visible
    fi
    
    echo "Starting FastAPI App (uvicorn)..."
    # Start the FastAPI worker app
    exec uvicorn worker_app_fastwan.main:app --host 0.0.0.0 --port 8000 &
    API_PID=$!
    
    # Wait for either process to exit
    wait -n "$WORKER_PID" "$API_PID"
    
    exit $?
fi
