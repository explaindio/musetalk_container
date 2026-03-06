# SaladCloud GPU Pricing & Availability

**Last updated:** 2026-03-04 08:50 

Prices shown are **batch** priority (cheapest tier). Availability = nodes ready now at batch pricing.

To refresh: `export $(grep -v '^#' .env | grep -v '^$' | xargs) && python3 refresh_salad_pricing.py`

## GTX 10xx / 16xx Series

| GPU | VRAM | Batch $/hr | Batch $/mo | Avail (batch) | On-Call |
|-----|------|-----------|-----------|--------------|--------|
| GTX 1050 Ti | 4 GB | $0.015 | $10.9 | 14 | 72 |
| GTX 1060 | 6 GB | $0.02 | $14.6 | 15 | 82 |
| GTX 1070, 1080, 1080Ti | 8 GB | $0.02 | $14.6 | 24 | 183 |
| GTX 1650 | 4 GB | $0.015 | $10.9 | 18 | 190 |
| GTX 1660 | 6 GB | $0.02 | $14.6 | 9 | 69 |
| GTX 1660 Super | 6 GB | $0.02 | $14.6 | 10 | 117 |

## RTX 20xx Series

| GPU | VRAM | Batch $/hr | Batch $/mo | Avail (batch) | On-Call |
|-----|------|-----------|-----------|--------------|--------|
| RTX 2060 | 6 GB | $0.02 | $14.6 | 32 | 185 |
| RTX 2070 | 8 GB | $0.02 | $14.6 | 19 | 107 |
| RTX 2080 Ti | 11 GB | $0.06 | $43.8 | 31 | 91 |
| RTX 2080 | 8 GB | $0.05 | $36.5 | 13 | 61 |

## RTX 30xx Series

| GPU | VRAM | Batch $/hr | Batch $/mo | Avail (batch) | On-Call |
|-----|------|-----------|-----------|--------------|--------|
| RTX 3050 | 8 GB | $0.03 | $21.9 | 10 | 84 |
| RTX 3060 | 12 GB | $0.04 | $29.2 | 315 | 1088 |
| RTX 3060 | 8 GB | $0.03 | $21.9 | 2 | 18 |
| RTX 3060 Ti | 8 GB | $0.03 | $21.9 | 144 | 604 |
| RTX 3070 Ti | 8 GB | $0.06 | $43.8 | 60 | 197 |
| RTX 3070 | 8 GB | $0.04 | $29.2 | 120 | 493 |
| RTX 3080 Ti | 12 GB | $0.08 | $58.4 | 68 | 244 |
| RTX 3080 | 10 GB | $0.06 | $43.8 | 110 | 452 |
| RTX 3090 | 24 GB | $0.09 | $65.7 | 227 | 1330 |
| RTX 3090 Ti | 24 GB | $0.1 | $73.0 | 41 | 109 |

## RTX 40xx Series

| GPU | VRAM | Batch $/hr | Batch $/mo | Avail (batch) | On-Call |
|-----|------|-----------|-----------|--------------|--------|
| RTX 4060 Ti | 16 GB | $0.08 | $58.4 | 128 | 298 |
| RTX 4070 Ti | 12 GB | $0.08 | $58.4 | 48 | 219 |
| RTX 4070 | 12 GB | $0.07 | $51.1 | 133 | 597 |
| RTX 4070 Ti Super | 16 GB | $0.09 | $65.7 | 50 | 430 |
| RTX 4080 | 16 GB | $0.11 | $80.3 | 114 | 353 |
| RTX 4090 | 24 GB | $0.16 | $116.8 | 291 | 953 |

## RTX 50xx Series

| GPU | VRAM | Batch $/hr | Batch $/mo | Avail (batch) | On-Call |
|-----|------|-----------|-----------|--------------|--------|
| RTX 5060 Ti | 16 GB | $0.07 | $51.1 | 55 | 212 |
| RTX 5070 | 12 GB | $0.08 | $58.4 | 149 | 529 |
| RTX 5070 Ti | 16 GB | $0.1 | $73.0 | 66 | 375 |
| RTX 5080 | 16 GB | $0.18 | $131.4 | 91 | 382 |
| RTX 5090 | 32 GB | $0.25 | $182.5 | 163 | 544 |

## Professional / Workstation

| GPU | VRAM | Batch $/hr | Batch $/mo | Avail (batch) | On-Call |
|-----|------|-----------|-----------|--------------|--------|
| RTX A5000 | 24 GB | $0.09 | $65.7 | 2 | 7 |

---

## API Reference

```bash
# Check availability for a specific GPU
export $(grep -v '^#' .env | grep -v '^$' | xargs) && curl -s -X POST \
  "https://api.salad.com/api/public/organizations/$SALAD_ORG_NAME/availability/sce-gpu-availability" \
  -H "Salad-Api-Key: $SALAD_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"gpu_classes":["<GPU_CLASS_ID>"]}'
```
