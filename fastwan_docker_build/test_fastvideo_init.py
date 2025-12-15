#!/usr/bin/env python3
"""
FastVideo Multiprocessing Executor Test Script

This script tests that the FastVideo VideoGenerator initializes correctly
with the multiprocessing executor. If this works, video generation will work.

Usage:
    python3 test_fastvideo_init.py

Expected output:
    SUCCESS! Generator initialized in XXX.XXs
    Multiprocessing executor is WORKING!
"""
import os
import sys
import time

# Set environment variable BEFORE any imports
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'

def main():
    import torch
    
    print('=' * 70)
    print('FASTVIDEO MULTIPROCESSING EXECUTOR TEST')
    print('=' * 70)
    print(f'PyTorch Version: {torch.__version__}')
    print(f'CUDA Available: {torch.cuda.is_available()}')
    
    if torch.cuda.is_available():
        print(f'GPU: {torch.cuda.get_device_name()}')
        print(f'Compute Capability: {torch.cuda.get_device_capability()}')
        print(f'CUDA Arch List: {torch.cuda.get_arch_list()}')
        print(f'GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB')
        
        # Check for sm_120 (Blackwell) support
        arch_list = torch.cuda.get_arch_list()
        if 'sm_120' in arch_list:
            print('✓ sm_120 (Blackwell/RTX 5090) support: YES')
        else:
            print('✗ sm_120 (Blackwell/RTX 5090) support: NO')
            print('  WARNING: This PyTorch build may not work on RTX 5090!')
    else:
        print('ERROR: CUDA not available!')
        sys.exit(1)
    
    print()
    print('-' * 70)
    print('Testing FastVideo import and initialization...')
    print('-' * 70)
    
    from fastvideo import VideoGenerator
    print('✓ FastVideo imported successfully')
    
    print()
    print('Initializing VideoGenerator with num_gpus=1...')
    print('(This will download model weights on first run, ~10GB)')
    print()
    
    start_time = time.time()
    
    try:
        generator = VideoGenerator.from_pretrained(
            'FastVideo/FastWan2.2-TI2V-5B-Diffusers',
            num_gpus=1,
        )
        
        load_time = time.time() - start_time
        
        print()
        print('=' * 70)
        print(f'✓ SUCCESS! Generator initialized in {load_time:.2f}s')
        print('✓ Multiprocessing executor is WORKING!')
        print('=' * 70)
        
        # Clean shutdown
        print()
        print('Shutting down generator...')
        generator.shutdown()
        print('✓ Generator shutdown complete')
        
        return 0
        
    except Exception as e:
        print()
        print('=' * 70)
        print(f'✗ FAILED: {e}')
        print('=' * 70)
        import traceback
        traceback.print_exc()
        
        # Common failure diagnosis
        print()
        print('--- DIAGNOSIS ---')
        error_str = str(e).lower()
        if 'multiproc' in error_str or 'spawn' in error_str:
            print('This appears to be a multiprocessing/spawn issue.')
            print('Possible fixes:')
            print('  1. Run container with --ipc=host')
            print('  2. Run container with --shm-size=8g')
            print('  3. Try distributed_executor_backend="ray"')
        elif 'sm_120' in error_str or 'kernel' in error_str:
            print('This appears to be a CUDA kernel compatibility issue.')
            print('The PyTorch build does not have sm_120 kernels.')
        
        return 1


if __name__ == '__main__':
    sys.exit(main())
