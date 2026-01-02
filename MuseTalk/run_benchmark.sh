#!/usr/bin/env bash
set -euo pipefail

# Optional label for this run, can be set per Salad deployment
GPU_SKU="${GPU_SKU:-unknown}"

rm -f /tmp/vram_log.csv /tmp/time.log /tmp/inference_stdout.log || true

# Start lightweight VRAM sampler
nvidia-smi --query-gpu=timestamp,memory.used --format=csv -lms 200 -f /tmp/vram_log.csv &
SMPID=$!

# Run inference with detailed timing; capture stdout and time's stderr
/usr/bin/time -v python -m scripts.inference \
  --inference_config configs/inference/test_docker.yaml \
  --result_dir results/test_benchmark \
  --unet_model_path models/musetalkV15/unet.pth \
  --unet_config models/musetalkV15/musetalk.json \
  --version v15 \
  --use_float16 2> /tmp/time.log | tee /tmp/inference_stdout.log

STATUS=$?
kill "$SMPID" || true
sleep 1

# Fallbacks in case parsing fails
GEN_SEC=""
SCRIPT_SEC=""

GEN_LINE="$(grep 'Generation time (model inference loop)' /tmp/inference_stdout.log | tail -n 1 || true)"
SCRIPT_LINE="$(grep 'Total script wall time (main)' /tmp/inference_stdout.log | tail -n 1 || true)"

if [[ -n "$GEN_LINE" ]]; then
  # Expected format: "Generation time (model inference loop): 24.374 seconds"
  GEN_SEC="$(echo "$GEN_LINE" | awk -F': ' '{print $2}' | awk '{print $1}')"
fi

if [[ -n "$SCRIPT_LINE" ]]; then
  # Expected format: "Total script wall time (main): 162.729 seconds"
  SCRIPT_SEC="$(echo "$SCRIPT_LINE" | awk -F': ' '{print $2}' | awk '{print $1}')"
fi

# Peak VRAM from nvidia-smi log (MiB)
PEAK_VRAM_MIB="$(
  tail -n +2 /tmp/vram_log.csv 2>/dev/null | \
    awk -F',' '{
      gsub(/ MiB/,"",$2);
      gsub(/^ +/,"",$2);
      if ($2>max) max=$2
    }
    END {
      if (max>0) print max; else print "0"
    }'
)"

# Peak RAM from /usr/bin/time (kB)
MAX_RSS_KB="$(awk '/Maximum resident set size/ {print $6}' /tmp/time.log || echo "")"

echo "=== BENCHMARK SUMMARY ==="
echo "GPU_SKU=${GPU_SKU}"
echo "EXIT_STATUS=${STATUS}"
echo "GENERATION_TIME_SEC=${GEN_SEC}"
echo "SCRIPT_WALL_TIME_SEC=${SCRIPT_SEC}"
echo "PEAK_VRAM_MIB=${PEAK_VRAM_MIB}"
echo "PEAK_RAM_KB=${MAX_RSS_KB}"

if [[ -n "$GEN_LINE" ]]; then
  echo "GENERATION_LINE=${GEN_LINE}"
fi
if [[ -n "$SCRIPT_LINE" ]]; then
  echo "SCRIPT_LINE=${SCRIPT_LINE}"
fi

exit "$STATUS"

