FROM nvidia/cuda:11.8.0-runtime-ubuntu22.04

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip ffmpeg git time && \
    rm -rf /var/lib/apt/lists/*

# Copy MuseTalk repo (including models we already downloaded)
COPY MuseTalk /app

# Copy test inputs for container validation
COPY girl_foravatar_talking.mp4 audio_kokoro_x2.wav /app/test_inputs/

# Ensure benchmark script is executable
RUN chmod +x run_benchmark.sh

# Create virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Install core Python deps
RUN pip install --upgrade pip && \
    pip install torch==2.0.1+cu118 torchvision==0.15.2+cu118 torchaudio==2.0.2+cu118 \
        --index-url https://download.pytorch.org/whl/cu118 && \
    pip install -r requirements.txt

# Install MMLab stack
RUN pip install --no-cache-dir -U openmim && \
    mim install mmengine && \
    mim install "mmcv==2.0.1" && \
    mim install "mmdet==3.1.0"

# mmpose + chumpy dependency
RUN pip install --no-build-isolation chumpy==0.70 && \
    mim install "mmpose==1.1.0"

ENTRYPOINT ["bash", "run_benchmark.sh"]
