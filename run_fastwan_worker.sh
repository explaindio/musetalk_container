#!/usr/bin/env bash
set -euo pipefail

echo "=== FastWan Worker Starting ==="
echo "Date: $(date)"

# ============================================================================
# SHARED MEMORY CHECK & WORKAROUND
# FastVideo multiprocessing requires large shared memory (8GB+)
# Docker default is only 64MB which causes WorkerMultiprocProc to fail
# ============================================================================
SHM_SIZE=$(df -h /dev/shm 2>/dev/null | tail -1 | awk '{print $2}' || echo "unknown")
echo "Shared Memory (/dev/shm): $SHM_SIZE"

# If shm is less than 1GB, warn loudly
if [ -f /dev/shm ]; then
    SHM_BYTES=$(df /dev/shm | tail -1 | awk '{print $2}')
    if [ "$SHM_BYTES" -lt 1000000 ]; then
        echo "WARNING: /dev/shm is too small! FastVideo needs --shm-size=8g"
        echo "Add to Salad container config: shm_size: 8589934592 (8GB in bytes)"
    fi
fi

# ============================================================================
# ENVIRONMENT SETUP
# ============================================================================
export PYTHONPATH="/workspace:${PYTHONPATH:-}"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"

# Force spawn method for multiprocessing (required in containers)
export PYTHONFAULTHANDLER=1

WORKER_MODE="${WORKER_MODE:-queue}"
echo "WORKER_MODE: $WORKER_MODE"
echo "CUDA_VISIBLE_DEVICES: $CUDA_VISIBLE_DEVICES"

# ============================================================================
# PYTORCH & GPU CHECK
# ============================================================================
python -c "
import torch
print(f'PyTorch: {torch.__version__}')
print(f'CUDA available: {torch.cuda.is_available()}')
if torch.cuda.is_available():
    print(f'GPU: {torch.cuda.get_device_name(0)}')
    print(f'Compute Capability: {torch.cuda.get_device_capability(0)}')
    print(f'VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB')
"

# ============================================================================
# MULTIPROCESSING TEST
# This tests if Python multiprocessing spawn works in this container
# ============================================================================
echo "Testing multiprocessing spawn..."
python -c "
import multiprocessing as mp
import sys

try:
    mp.set_start_method('spawn', force=True)
except RuntimeError:
    pass

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
        print('This likely means --shm-size is too small!')
        sys.exit(1)
"

echo "==============================="

# ============================================================================
# START WORKER
# ============================================================================
if [ "$WORKER_MODE" = "buffer" ]; then
    echo "Starting FastWan worker in BUFFER mode..."
    exec python -m worker_app_fastwan.main
else
    echo "Starting FastWan worker in QUEUE mode (Salad)..."
    
    # Start the Salad HTTP Job Queue Worker in the background
    /usr/local/bin/salad-http-job-queue-worker &
    WORKER_PID=$!
    
    # Start the FastAPI worker app
    exec uvicorn worker_app_fastwan.main:app --host 0.0.0.0 --port 8000 &
    API_PID=$!
    
    # Wait for either process to exit
    wait -n "$WORKER_PID" "$API_PID"
    
    exit $?
fi
