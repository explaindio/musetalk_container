# FastVideo/FastWan Docker Image for RTX 5090 (Blackwell)
# 
# This Dockerfile replicates the EXACT working environment tested on Vast.ai
# that successfully ran FastVideo's multiprocessing executor.
#
# Tested on: December 15, 2025
# GPU: NVIDIA GeForce RTX 5090 (32GB VRAM, sm_120)
# Result: SUCCESS - multiprocessing executor works
#
# Build: docker build -t fastvideo-5090:latest .
# Run:   docker run --gpus all --ipc=host --shm-size=8g fastvideo-5090:latest

# Use the same base image that worked on Vast.ai
FROM pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
ENV PYTHONUNBUFFERED=1

# System dependencies
RUN apt-get update && apt-get install -y \
    git \
    libgl1-mesa-glx \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Install PyTorch with CUDA 12.8 and sm_120 (Blackwell) support
# This is the CRITICAL step - must have sm_120 in arch list
RUN pip install --pre torch torchvision --index-url https://download.pytorch.org/whl/nightly/cu128 --force-reinstall

# Install dependencies BEFORE FastVideo to control versions
# numpy<2.0 is CRITICAL - FastVideo/scipy breaks with numpy 2.x
RUN pip install "numpy<2.0" \
    diffusers \
    transformers \
    accelerate \
    safetensors \
    einops \
    sentencepiece \
    huggingface_hub \
    imageio \
    imageio-ffmpeg \
    opencv-python \
    ftfy

# Clone and install FastVideo from source
WORKDIR /workspace
RUN git clone https://github.com/hao-ai-lab/FastVideo.git && \
    cd FastVideo && \
    pip install -e .

# Apply 720p resolution patch (allows 720p generation, default is 480p max)
RUN sed -i 's/max_area = 480 \* 832/max_area = 720 \* 1280/' \
    /workspace/FastVideo/fastvideo/pipelines/stages/input_validation.py

# Copy test script and worker script
COPY test_fastvideo_init.py /workspace/test_fastvideo_init.py
COPY generate_video.py /workspace/generate_video.py

# Create directory for outputs
RUN mkdir -p /workspace/outputs

# Default working directory
WORKDIR /workspace

# Verify installation at build time
RUN python3 -c "import torch; print(f'PyTorch: {torch.__version__}'); \
    print(f'CUDA available: {torch.cuda.is_available()}'); \
    print(f'Arch list: {torch.cuda.get_arch_list() if torch.cuda.is_available() else \"N/A\"}')"

# Default command - run the init test
CMD ["python3", "-u", "test_fastvideo_init.py"]
