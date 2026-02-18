#!/bin/bash
# A/B test: original vs optimized inference script
# Run inside Docker container with GPU access
set -e

cd /app/MuseTalk

# Create test inference config
cat > /tmp/test_config.yaml << 'EOF'
test_job:
  video_path: "./data/video/sun.mp4"
  audio_path: "./data/audio/sun.wav"
  result_name: "test_output.mp4"
EOF

echo "========================================="
echo "TEST 1: ORIGINAL inference.py (disk-based)"
echo "========================================="
rm -rf results/v15/test_output.mp4 2>/dev/null || true
time python -m scripts.inference \
  --inference_config /tmp/test_config.yaml \
  --result_dir results \
  --version v15 \
  --use_float16 \
  --batch_size 8 \
  --output_vid_name test_original.mp4 \
  2>&1 | tee /tmp/original_output.log

echo ""
echo "========================================="
echo "TEST 2: OPTIMIZED inference_optimized.py (pipe-based)"
echo "========================================="
rm -rf results/v15/test_output.mp4 2>/dev/null || true
time python -m scripts.inference_optimized \
  --inference_config /tmp/test_config.yaml \
  --result_dir results \
  --version v15 \
  --use_float16 \
  --batch_size 8 \
  --output_vid_name test_optimized.mp4 \
  2>&1 | tee /tmp/optimized_output.log

echo ""
echo "========================================="
echo "RESULTS COMPARISON"
echo "========================================="
echo "Original wall time:"
grep "Total script wall time" /tmp/original_output.log
echo "Optimized wall time:"
grep "Total script wall time" /tmp/optimized_output.log

echo ""
echo "Original gen time:"
grep "Generation time" /tmp/original_output.log
echo "Optimized gen+encode time:"
grep "Generation + encoding time" /tmp/optimized_output.log

echo ""
echo "Original VRAM:"
grep "Peak VRAM" /tmp/original_output.log
echo "Optimized VRAM:"
grep "Peak VRAM" /tmp/optimized_output.log

echo ""
echo "Output file sizes:"
ls -lh results/v15/test_original.mp4 results/v15/test_optimized.mp4 2>/dev/null
