# FastVideo RTX 5090 Docker Build Instructions

## For Docker Builder

This package contains everything needed to build a Docker container that runs FastVideo (FastWan 2.2) on NVIDIA RTX 5090 GPUs (Blackwell architecture, sm_120).

**This configuration was tested and VERIFIED WORKING on December 15, 2025 on a Vast.ai RTX 5090 instance.**

---

## ⚠️ CRITICAL INFORMATION

### The Problem You're Solving
FastVideo uses a **multiprocessing executor** that spawns worker processes. This can fail in Docker containers due to:
1. IPC namespace restrictions
2. Limited shared memory (/dev/shm)
3. Security restrictions on process spawning

### The Tested Working Configuration
On Vast.ai (which also runs Docker containers), this setup works WITHOUT special flags. However, for other cloud providers like Salad Cloud, you may need:

```bash
docker run --gpus all --ipc=host --shm-size=8g <image>
```

---

## Files Included

| File | Description |
|------|-------------|
| `Dockerfile` | Main Dockerfile that replicates working Vast.ai environment |
| `requirements.txt` | Python dependencies (PyTorch installed separately) |
| `test_fastvideo_init.py` | Test script to verify multiprocessing executor works |
| `generate_video.py` | Production video generation script |
| `docker-compose.yml` | Docker Compose with correct settings |
| `README.md` | This file |

---

## Build Instructions

### Option 1: Standard Docker Build
```bash
cd fastwan_docker_build
docker build -t fastvideo-5090:latest .
```

### Option 2: Docker Compose
```bash
cd fastwan_docker_build
docker-compose build
```

---

## Run Instructions

### Test Multiprocessing Executor
This should be your first test after building:

```bash
# Standard Docker run (try this first)
docker run --gpus all fastvideo-5090:latest

# If above fails, use IPC host mode
docker run --gpus all --ipc=host --shm-size=8g fastvideo-5090:latest
```

**Expected output:**
```
✓ SUCCESS! Generator initialized in XXX.XXs
✓ Multiprocessing executor is WORKING!
```

### Generate a Video
```bash
docker run --gpus all --ipc=host --shm-size=8g \
    -v $(pwd)/inputs:/workspace/inputs:ro \
    -v $(pwd)/outputs:/workspace/outputs \
    fastvideo-5090:latest \
    python3 -u generate_video.py \
        --image /workspace/inputs/avatar.png \
        --prompt "She speaks with calm energy, gentle nods..." \
        --output /workspace/outputs/video.mp4 \
        --width 480 --height 848 \
        --num-frames 121
```

### Interactive Shell
```bash
docker run --gpus all --ipc=host --shm-size=8g -it fastvideo-5090:latest /bin/bash
```

---

## Technical Details

### PyTorch Version
The Dockerfile installs PyTorch nightly with CUDA 12.8 wheels:
```bash
pip install --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/cu128 --force-reinstall
```

After FastVideo installation, the final PyTorch version is **2.9.0+cu128** which includes:
- **sm_120** (RTX 5090 / Blackwell) ✅
- sm_100, sm_90, sm_86, sm_80, sm_75, sm_70

### Critical Dependencies
- **numpy < 2.0** - FastVideo/scipy breaks with numpy 2.x
- **diffusers** - From PyPI (FastVideo overrides with dev version)
- **FastVideo** - Installed from GitHub source

### Model Weights
The model `FastVideo/FastWan2.2-TI2V-5B-Diffusers` (~10GB) is downloaded from HuggingFace on first run. To pre-cache:

```bash
# Inside container or during build
huggingface-cli download FastVideo/FastWan2.2-TI2V-5B-Diffusers
```

Or mount a persistent volume to `/root/.cache/huggingface/hub`.

### Resolution Patch
The Dockerfile patches FastVideo to allow 720p output:
```bash
sed -i 's/max_area = 480 \* 832/max_area = 720 \* 1280/' \
    /workspace/FastVideo/fastvideo/pipelines/stages/input_validation.py
```

| Resolution | Dimensions | VRAM Usage | Generation Time (5s video) |
|------------|------------|------------|---------------------------|
| 480p | 480x848 | ~16-18 GB | ~15s |
| 720p | 720x1280 | ~28-30 GB | ~38s |

---

## Troubleshooting

### Error: `WorkerMultiprocProc failed to start`
This is a multiprocessing spawn failure. Try:
1. Add `--ipc=host` to docker run
2. Add `--shm-size=8g` to docker run
3. Check if cloud provider blocks process spawning

### Error: `no kernel image is available for execution on the device`
PyTorch doesn't have sm_120 kernels. Verify with:
```python
import torch
print(torch.cuda.get_arch_list())  # Should include 'sm_120'
```

### Error: `numpy` related
Ensure numpy < 2.0:
```bash
pip install "numpy<2.0"
```

### Error: `An attempt has been made to start a new process before...`
Your Python script needs:
```python
if __name__ == '__main__':
    main()
```

---

## Salad Cloud Specific

If deploying to Salad Cloud and multiprocessing fails, alternatives:

### Option 1: Use Ray Executor
Modify the code to use Ray instead of multiprocessing:
```python
generator = VideoGenerator.from_pretrained(
    'FastVideo/FastWan2.2-TI2V-5B-Diffusers',
    num_gpus=1,
    distributed_executor_backend="ray",  # Use Ray instead of mp
)
```
Requires adding `pip install ray` to the Dockerfile.

### Option 2: Use Diffusers Directly
If FastVideo multiprocessing doesn't work, use diffusers directly (slower but always works):
```python
from diffusers import WanImageToVideoPipeline
pipe = WanImageToVideoPipeline.from_pretrained(
    "Wan-AI/Wan2.2-I2V-A14B-Diffusers",
    torch_dtype=torch.bfloat16,
)
pipe.enable_sequential_cpu_offload()
```

---

## Verification Checklist

Before deploying, verify:

- [ ] `docker build` completes successfully
- [ ] PyTorch shows `sm_120` in arch list
- [ ] `test_fastvideo_init.py` outputs "SUCCESS! Multiprocessing executor is WORKING!"
- [ ] Video generation completes with test image

---

## Contact / Source

- FastVideo GitHub: https://github.com/hao-ai-lab/FastVideo
- Model: https://huggingface.co/FastVideo/FastWan2.2-TI2V-5B-Diffusers
- This configuration tested on Vast.ai RTX 5090 instance

---

## Quick Reference

```bash
# Build
docker build -t fastvideo-5090:latest .

# Test (try without flags first, add if needed)
docker run --gpus all --ipc=host --shm-size=8g fastvideo-5090:latest

# Generate video
docker run --gpus all --ipc=host --shm-size=8g \
    -v ./inputs:/workspace/inputs:ro \
    -v ./outputs:/workspace/outputs \
    fastvideo-5090:latest \
    python3 generate_video.py --image /workspace/inputs/img.png --prompt "motion description"
```
