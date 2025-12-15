#!/usr/bin/env python3
"""
FastWan 2.2 Video Generation Script

This script generates a video from an input image using FastVideo/FastWan.

Usage:
    python3 generate_video.py --image /path/to/image.png --prompt "Your prompt"

Environment Variables:
    PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True (set automatically)
"""
import os
import sys
import time
import argparse

# Set environment variable BEFORE any imports
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'


def parse_args():
    parser = argparse.ArgumentParser(description='Generate video from image using FastWan')
    parser.add_argument('--image', type=str, required=True,
                        help='Path to input image')
    parser.add_argument('--prompt', type=str, required=True,
                        help='Text prompt describing desired motion')
    parser.add_argument('--output', type=str, default='/workspace/outputs/output.mp4',
                        help='Output video path (default: /workspace/outputs/output.mp4)')
    parser.add_argument('--width', type=int, default=480,
                        help='Video width (default: 480, use 720 for 720p)')
    parser.add_argument('--height', type=int, default=848,
                        help='Video height (default: 848, use 1280 for 720p)')
    parser.add_argument('--num-frames', type=int, default=121,
                        help='Number of frames (default: 121 = 5 seconds at 24fps)')
    parser.add_argument('--steps', type=int, default=4,
                        help='Number of inference steps (default: 4)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed (default: 42)')
    parser.add_argument('--guidance-scale', type=float, default=1.0,
                        help='Guidance scale (default: 1.0)')
    return parser.parse_args()


def main():
    args = parse_args()
    
    # Validate input image exists
    if not os.path.exists(args.image):
        print(f'ERROR: Input image not found: {args.image}')
        sys.exit(1)
    
    import torch
    
    print('=' * 70)
    print('FASTWAN 2.2 VIDEO GENERATION')
    print('=' * 70)
    print(f'PyTorch: {torch.__version__}')
    print(f'GPU: {torch.cuda.get_device_name()}')
    print(f'GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB')
    print()
    print('Settings:')
    print(f'  Input Image: {args.image}')
    print(f'  Output: {args.output}')
    print(f'  Resolution: {args.width}x{args.height}')
    print(f'  Frames: {args.num_frames}')
    print(f'  Steps: {args.steps}')
    print(f'  Seed: {args.seed}')
    print(f'  Guidance Scale: {args.guidance_scale}')
    print(f'  Prompt: {args.prompt[:100]}...' if len(args.prompt) > 100 else f'  Prompt: {args.prompt}')
    print()
    
    from fastvideo import VideoGenerator
    
    print('Loading FastWan model...')
    load_start = time.time()
    
    generator = VideoGenerator.from_pretrained(
        'FastVideo/FastWan2.2-TI2V-5B-Diffusers',
        num_gpus=1,
    )
    
    load_time = time.time() - load_start
    print(f'Model loaded in {load_time:.2f}s')
    print()
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output) or '.', exist_ok=True)
    
    print('Generating video...')
    print('-' * 70)
    
    gen_start = time.time()
    
    generator.generate_video(
        prompt=args.prompt,
        image_path=args.image,
        num_frames=args.num_frames,
        width=args.width,
        height=args.height,
        num_inference_steps=args.steps,
        output_path=args.output,
        save_video=True,
        seed=args.seed,
        guidance_scale=args.guidance_scale,
    )
    
    gen_time = time.time() - gen_start
    
    print()
    print('=' * 70)
    print('GENERATION COMPLETE')
    print('=' * 70)
    print(f'Output: {args.output}')
    print(f'Generation time: {gen_time:.2f}s')
    print(f'Frames: {args.num_frames}')
    print(f'FPS: {args.num_frames / gen_time:.2f}')
    print()
    
    # Clean shutdown
    generator.shutdown()
    print('Generator shutdown complete.')
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
