import os
import torch
import logging
import time
from typing import Optional, Dict, Any
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
        start = time.time()
        
        # Initialize Generator
        # num_gpus=1 for now.
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
        
        # Set allocator to avoid fragmentation (important for 5090/Blackwell)
        os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
        
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
