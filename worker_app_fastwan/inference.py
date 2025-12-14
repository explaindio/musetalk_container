import os
import sys
import torch
import logging
import time
import multiprocessing
from typing import Optional, Dict, Any

# CRITICAL: Set multiprocessing start method before importing fastvideo
# This fixes "WorkerMultiprocProc failed to start" in container environments
if __name__ != "__main__":
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass  # Already set

# Set environment variables before imports
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
os.environ["CUDA_VISIBLE_DEVICES"] = "0"  # Force single GPU

from fastvideo import VideoGenerator

logger = logging.getLogger(__name__)

class FastWanInference:
    def __init__(self):
        self.generator = None
        self.model_id = "FastVideo/FastWan2.2-TI2V-5B-Diffusers"
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

    def load_model(self):
        if self.generator is not None:
            return

        logger.info(f"Loading FastWan model from {self.model_id}...")
        logger.info(f"PyTorch version: {torch.__version__}")
        logger.info(f"CUDA available: {torch.cuda.is_available()}")
        if torch.cuda.is_available():
            logger.info(f"CUDA device: {torch.cuda.get_device_name(0)}")
            logger.info(f"CUDA capability: {torch.cuda.get_device_capability(0)}")
        
        start = time.time()
        
        # Initialize Generator with explicit single GPU
        self.generator = VideoGenerator.from_pretrained(
            self.model_id,
            num_gpus=1,
        )
        
        logger.info(f"Model loaded in {time.time() - start:.2f}s")

    def generate(
        self,
        image_path: str,
        prompt: str,
        num_frames: int,
        width: int,
        height: int,
        steps: int,
        seed: int,
        guidance_scale: float,
        output_path: str
    ) -> Dict[str, Any]:
        
        if self.generator is None:
            self.load_model()
            
        logger.info(f"Starting generation: {width}x{height} @ {num_frames} frames")
        
        start_time = time.time()
        
        self.generator.generate_video(
            prompt=prompt,
            image_path=image_path,
            num_frames=num_frames,
            width=width,
            height=height,
            num_inference_steps=steps,
            output_path=output_path,
            save_video=True,
            seed=seed,
            guidance_scale=guidance_scale
        )
        
        duration = time.time() - start_time
        logger.info(f"Generation complete in {duration:.2f}s")
        
        # Get peak VRAM usage
        peak_vram = 0
        if torch.cuda.is_available():
            peak_vram = torch.cuda.max_memory_allocated() / (1024 ** 3)
            torch.cuda.reset_peak_memory_stats()
            
        return {
            "duration_sec": duration,
            "peak_vram_gb": peak_vram,
            "fps": num_frames / duration if duration > 0 else 0
        }
