#!/usr/bin/env python3
"""
Refresh Salad GPU pricing and availability data.
Generates SALAD_GPU_PRICING.md with tables by GPU generation.

Usage: source .env && python3 refresh_salad_pricing.py
"""
import asyncio, httpx, os, sys
from datetime import datetime

KEY = os.environ.get('SALAD_API_KEY', '')
ORG = os.environ.get('SALAD_ORG_NAME', 'explaindiolls')
BASE = f'https://api.salad.com/api/public/organizations/{ORG}'
HDRS = {'Salad-Api-Key': KEY, 'Content-Type': 'application/json'}

GENERATIONS = {
    "GTX 10xx / 16xx Series": lambda n: "GTX" in n,
    "RTX 20xx Series": lambda n: "RTX 2" in n,
    "RTX 30xx Series": lambda n: "RTX 30" in n,
    "RTX 40xx Series": lambda n: "RTX 4" in n,
    "RTX 50xx Series": lambda n: "RTX 5" in n,
    "Professional / Workstation": lambda n: "RTX A" in n,
}

# Sort order within each generation (extract numeric model number)
def sort_key(name):
    import re
    nums = re.findall(r'\d+', name)
    return int(nums[0]) if nums else 0

async def fetch_avail(client, gid):
    try:
        r = await client.post(f'{BASE}/availability/sce-gpu-availability',
            headers=HDRS, json={'gpu_classes': [gid]}, timeout=20)
        d = r.json()
        return d.get('available_gpu_batch', '?'), d.get('on_call_gpu', '?')
    except:
        return '?', '?'

async def main():
    if not KEY:
        print("Error: SALAD_API_KEY not set"); sys.exit(1)

    # 1. Fetch live pricing from API
    import requests
    print("Fetching GPU classes and pricing...")
    resp = requests.get(f'{BASE}/gpu-classes', headers=HDRS, timeout=30)
    gpu_list = resp.json().get('items', [])
    print(f"  Got {len(gpu_list)} GPU classes")

    # Build GPU info with live prices
    gpus = []
    for g in gpu_list:
        prices = {p['priority']: p['price'] for p in g.get('prices', [])}
        name = g['name']
        # Extract VRAM from name, e.g. "RTX 3090 (24 GB)" -> "24"
        import re
        vram_match = re.search(r'\((\d+)\s*GB\)', name)
        vram = vram_match.group(1) if vram_match else '?'
        # Clean name (remove VRAM part)
        clean_name = re.sub(r'\s*\(\d+\s*GB\)', '', name).strip()
        gpus.append({
            'id': g['id'],
            'name': clean_name,
            'full_name': name,
            'vram': vram,
            'batch': prices.get('batch', '?'),
            'low': prices.get('low', '?'),
            'medium': prices.get('medium', '?'),
            'high': prices.get('high', '?'),
        })

    # 2. Fetch availability in parallel
    print(f"Fetching availability for {len(gpus)} GPUs...")
    avail = {}
    async with httpx.AsyncClient() as client:
        tasks = {g['id']: asyncio.create_task(fetch_avail(client, g['id'])) for g in gpus}
        for gid, task in tasks.items():
            avail[gid] = await task
            name = [g['name'] for g in gpus if g['id'] == gid][0]
            ab, oc = avail[gid]
            print(f"  {name}: batch_avail={ab}, on_call={oc}")

    # 3. Generate markdown
    now = datetime.now().strftime("%Y-%m-%d %H:%M %Z")
    lines = [
        "# SaladCloud GPU Pricing & Availability",
        "",
        f"**Last updated:** {now}",
        "",
        "Prices shown are **batch** priority (cheapest tier). Availability = nodes ready now at batch pricing.",
        "",
        "To refresh: `export $(grep -v '^#' .env | grep -v '^$' | xargs) && python3 refresh_salad_pricing.py`",
        "",
    ]

    for gen_name, match_fn in GENERATIONS.items():
        gen_gpus = [g for g in gpus if match_fn(g['full_name'])]
        if not gen_gpus:
            continue
        gen_gpus.sort(key=lambda g: sort_key(g['name']))
        lines.append(f"## {gen_name}")
        lines.append("")
        lines.append("| GPU | VRAM | Batch $/hr | Batch $/mo | Avail (batch) | On-Call |")
        lines.append("|-----|------|-----------|-----------|--------------|--------|")
        for g in gen_gpus:
            ab, oc = avail.get(g['id'], ('?', '?'))
            batch = g['batch']
            try:
                monthly = f"${float(batch)*730:.1f}"
            except:
                monthly = '?'
            lines.append(f"| {g['name']} | {g['vram']} GB | ${batch} | {monthly} | {ab} | {oc} |")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("## API Reference")
    lines.append("")
    lines.append("```bash")
    lines.append("# Check availability for a specific GPU")
    lines.append('export $(grep -v \'^#\' .env | grep -v \'^$\' | xargs) && curl -s -X POST \\')
    lines.append('  "https://api.salad.com/api/public/organizations/$SALAD_ORG_NAME/availability/sce-gpu-availability" \\')
    lines.append('  -H "Salad-Api-Key: $SALAD_API_KEY" \\')
    lines.append('  -H "Content-Type: application/json" \\')
    lines.append("  -d '{\"gpu_classes\":[\"<GPU_CLASS_ID>\"]}'")
    lines.append("```")
    lines.append("")

    md = "\n".join(lines)
    with open("SALAD_GPU_PRICING.md", "w") as f:
        f.write(md)
    print(f"\nWritten to SALAD_GPU_PRICING.md")

asyncio.run(main())

