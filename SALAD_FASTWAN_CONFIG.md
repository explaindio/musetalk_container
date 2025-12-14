# FastWan Worker - Salad Cloud Configuration

## CRITICAL: Shared Memory Requirements

FastVideo uses Python multiprocessing which requires **large shared memory**.

### Required Salad Container Settings

In your Salad container configuration, you MUST set shared memory:

```json
{
  "container": {
    "image": "explaindio/fastwan-worker:v1",
    "resources": {
      "gpu_classes": ["rtx_5090"],
      "memory": 32768,
      "shm_size": 8589934592
    }
  }
}
```

Or in Docker equivalent:
```bash
docker run --gpus all --shm-size=8g explaindio/fastwan-worker:v1
```

### Why This Matters

- **Docker default**: `/dev/shm` is only 64MB
- **FastVideo needs**: At least 8GB shared memory
- **Symptom of failure**: `WorkerMultiprocProc failed to start`

### Verification

The container will output at startup:
```
Shared Memory (/dev/shm): 8.0G
Testing multiprocessing spawn...
Multiprocessing OK: [2, 4, 6]
```

If you see:
```
WARNING: /dev/shm is too small! FastVideo needs --shm-size=8g
Multiprocessing FAILED: ...
```

Then shared memory is not configured correctly.

## Salad Dashboard Configuration

1. Go to Container Group settings
2. Find "Advanced" or "Container Resources" section
3. Look for "Shared Memory" or "shm_size"
4. Set to: `8589934592` (8GB in bytes) or `8g`

## Alternative: IPC Host Mode

If Salad supports it:
```json
{
  "container": {
    "ipc_mode": "host"
  }
}
```

This shares the host's IPC namespace (including shared memory) with the container.

## RTX 5090 Requirements

- **CUDA**: 12.8+ (for sm_120 / Blackwell support)
- **PyTorch**: Nightly build with cu128
- **VRAM**: 32GB (5090 has 32GB)
- **SHM**: 8GB minimum

## Environment Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `WORKER_MODE` | `queue` or `buffer` | Job source |
| `CUDA_VISIBLE_DEVICES` | `0` (default) | GPU selection |
| `PYTORCH_CUDA_ALLOC_CONF` | `expandable_segments:True` | Memory allocation |
