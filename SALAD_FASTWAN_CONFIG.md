# FastWan Worker - Salad Cloud Configuration

## CRITICAL: Docker Runtime Requirements

FastVideo uses a **multiprocessing spawn executor** that requires specific Docker flags.

### Required Docker Flags

```bash
docker run --gpus all --ipc=host --shm-size=8g explaindio/fastwan-worker:v1
```

| Flag | Why It's Needed | Default |
|------|-----------------|---------|
| `--gpus all` | GPU access | N/A |
| `--ipc=host` | **CRITICAL** - Allows multiprocessing spawn between processes | Isolated |
| `--shm-size=8g` | Increases /dev/shm from 64MB to 8GB | 64MB |

### Salad Container Configuration

In your Salad container configuration, you **MUST** set:

```json
{
  "container": {
    "image": "explaindio/fastwan-worker:v1",
    "resources": {
      "gpu_classes": ["rtx_5090"],
      "memory": 32768
    },
    "ipc_mode": "host",
    "shm_size": 8589934592
  }
}
```

Or in Salad dashboard:
- **IPC Mode**: Host
- **Shared Memory**: 8589934592 (8GB in bytes)

### The Problem Without These Settings

Without `--ipc=host`, FastVideo's multiprocessing executor fails with:

```
Exception: WorkerMultiprocProc initialization failed due to an exception in a background process.
```

This is NOT a code bug - it's a Docker container configuration issue.

### Verification Test

After starting the container, logs should show:

**✅ Success:**
```
=== FastWan Worker Starting ===
PyTorch: 2.6.0.dev...+cu128
CUDA available: True
GPU: NVIDIA GeForce RTX 5090
Multiprocessing OK: [2, 4, 6]
===============================
```

**❌ Failure (missing --ipc=host or --shm-size):**
```
WorkerMultiprocProc initialization failed
```

---

## If Salad Doesn't Support --ipc=host

If Salad Cloud does not support IPC host mode, here are alternatives:

### Option 1: Ray Executor

Modify the worker to use Ray instead of multiprocessing:

```python
generator = VideoGenerator.from_pretrained(
    'FastVideo/FastWan2.2-TI2V-5B-Diffusers',
    num_gpus=1,
    distributed_executor_backend="ray",  # Use Ray instead of mp
)
```

And add `pip install ray` to the Dockerfile.

### Option 2: Diffusers Directly

Use the diffusers library directly without FastVideo's multiprocessing wrapper. Slower but guaranteed to work.

---

## RTX 5090 Requirements

| Setting | Value |
|---------|-------|
| GPU | RTX 5090 (Blackwell, sm_120) |
| CUDA | 12.8+ |
| PyTorch | Nightly with cu128 (has sm_120 kernels) |
| VRAM | 32GB |
| Shared Memory | 8GB minimum |
| IPC Mode | Host (required for multiprocessing) |

---

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `WORKER_MODE` | `queue` | `queue` for Salad, `buffer` for Vast.ai |
| `CUDA_VISIBLE_DEVICES` | `0` | GPU selection |
| `PYTORCH_CUDA_ALLOC_CONF` | `expandable_segments:True` | Memory allocation |

---

## Tested Working Configuration

Tested on: **December 15, 2025**
Platform: **Vast.ai RTX 5090**
Result: **SUCCESS - multiprocessing executor works**

The Docker configuration in this repository replicates the exact working environment.
