# MuseTalk on Salad – 1 Job per GPU (Max Performance)

This document describes how to run MuseTalk on [Salad](https://salad.com) with **one inference job per GPU**, tuned for **maximum performance** (no artificial CPU/GPU limits).

The design:
- Each Salad job runs **one container**.
- Each container runs **one MuseTalk inference**.
- Each container requests **one GPU**, and is free to use whatever CPU resources the host provides.

---

## 1. Container Image

Base assumptions:
- CUDA‑enabled host with an NVIDIA GPU.
- Torch 2.0.1 + CUDA 11.8 (matching this repo’s README).

Example `Dockerfile` outline:

```Dockerfile
FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl ffmpeg python3 python3-venv python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Copy MuseTalk repo (or clone in the build step)
COPY . /app

# Create venv (optional but recommended)
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Install Python deps
RUN pip install --upgrade pip && \
    pip install torch==2.0.1+cu118 torchvision==0.15.2+cu118 torchaudio==2.0.2+cu118 \
        --index-url https://download.pytorch.org/whl/cu118 && \
    pip install -r requirements.txt

# MMLab stack
RUN pip install --no-cache-dir -U openmim && \
    mim install mmengine && \
    mim install "mmcv==2.0.1" && \
    mim install "mmdet==3.1.0" && \
    mim install "mmpose==1.1.0"

# Optional: pre-download all models into /app/models so jobs skip HF downloads
# (You can reuse the logic from download_weights.sh inside the image build
#  or in an initialization script.)

# Entrypoint will be set to our job runner
ENTRYPOINT ["python", "/app/run_job.py"]
```

Adjust the `COPY` step depending on how you build the image (monorepo, subdir, etc.).

---

## 2. Job Runner Script (`run_job.py`)

`run_job.py` is the single entry point for a Salad job. It should:

1. Parse job parameters:  
   - Provided via environment variables or a JSON file, e.g.:
     - `VIDEO_URL` – source video (e.g. MuseV result or avatar clip).
     - `AUDIO_URL` – source audio (WAV/MP3).
     - `OUTPUT_URL` – destination path/bucket key to upload the final MP4.
2. Download inputs into a local workspace, e.g. `/tmp/job_<id>/`.
3. Generate a minimal MuseTalk inference config YAML (one `task_0`).
4. Run MuseTalk once using `scripts.inference`.
5. Upload the output MP4 to `OUTPUT_URL`.
6. Exit with code 0 on success, non‑zero on failure.

Example skeleton:

```python
# /app/run_job.py
import os
import subprocess
import tempfile
import textwrap
from pathlib import Path

def sh(cmd, cwd=None):
    print(f"[run_job] $ {cmd}")
    subprocess.run(cmd, shell=True, check=True, cwd=cwd)

def main():
    video_url = os.environ["VIDEO_URL"]
    audio_url = os.environ["AUDIO_URL"]
    output_path = os.environ.get("OUTPUT_PATH", "/tmp/output.mp4")

    workdir = Path(tempfile.mkdtemp(prefix="musetalk_job_"))
    video_path = workdir / "input_video.mp4"
    audio_path = workdir / "input_audio"

    # Download inputs (replace with your preferred tool / auth mechanism)
    sh(f"curl -L '{video_url}' -o '{video_path}'")
    sh(f"curl -L '{audio_url}' -o '{audio_path}'")

    # Write a minimal inference config
    config_path = workdir / "job.yaml"
    config_path.write_text(textwrap.dedent(f"""
    task_0:
      video_path: "{video_path}"
      audio_path: "{audio_path}"
    """).strip() + "\n")

    # Run MuseTalk (1 job per GPU, no throttling)
    result_dir = workdir / "results"
    sh(
        "python -m scripts.inference "
        f"--inference_config {config_path} "
        f"--result_dir {result_dir} "
        "--unet_model_path models/musetalkV15/unet.pth "
        "--unet_config models/musetalkV15/musetalk.json "
        "--version v15 "
        "--use_float16 "
        "--use_saved_coord"
    , cwd="/app")

    # Find the output video (v15 subdir, any mp4)
    mp4_candidates = list(result_dir.rglob("*.mp4"))
    if not mp4_candidates:
        raise RuntimeError("No MP4 output found")
    final_mp4 = mp4_candidates[0]

    # Save or upload output (example: just copy to OUTPUT_PATH)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sh(f"cp '{final_mp4}' '{output_path}'")

if __name__ == "__main__":
    main()
```

In a real deployment you’d replace the `curl`/`cp` calls with your own storage (S3, GCS, etc.).

---

## 3. Salad Job Configuration

At the Salad level:

- **Container image:** the image built from the `Dockerfile` above.
- **GPU request:** `1` GPU per job (e.g. “1 x NVIDIA RTX 3090” or similar class).
- **CPU & RAM:** let Salad assign normal resources; no artificial limits in the container.
- **Command:** use the image `ENTRYPOINT` (no override), or explicitly:
  - `["python", "/app/run_job.py"]`
- **Environment variables per job:**
  - `VIDEO_URL`
  - `AUDIO_URL`
  - `OUTPUT_PATH` (or equivalent output spec)

Each job you submit to Salad becomes exactly one MuseTalk inference on one GPU.

---

## 4. Throughput Model (1 Job per GPU)

- Each Salad node runs **one container per GPU**.
- Each container runs **one inference** and then exits.
- You scale throughput by:
  - Increasing the number of GPUs (more Salad nodes).
  - Submitting more jobs; Salad schedules them on available GPUs.

No worker pool, no internal queue, no per‑job throttling—Salad’s scheduler handles parallelism across GPUs, and each GPU is dedicated to a single MuseTalk run at a time.

---

## 5. Optional Performance Knobs

These are **optional** and only used if you decide to tune further:

- `--use_float16` (already enabled in the example) keeps UNet/VAE/Whisper in fp16 for better speed and lower VRAM.
- `--batch_size` in `scripts.inference` can be increased if you know your target GPUs have additional VRAM headroom and you want more frames per GPU pass.
- `--use_saved_coord` is already in use above; if you implement avatar‑specific caching, you can pre‑compute and reuse landmark/pose data for repeated avatars to save time.

Nothing in this document caps CPU threads or otherwise “slows down” the job—each container is free to use the host GPU and CPU as aggressively as the underlying libraries allow. 

