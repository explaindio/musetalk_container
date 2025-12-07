#!/usr/bin/env python
"""
Submit a batch of avatar jobs via the orchestrator API and log
end-to-end wall time for the whole batch.

Usage (example, do NOT run until explicitly decided):

  python run_avatar_batch_test.py \\
    --batch-name batch450_1 \\
    --count 450

Configuration:
  - Reads INTERNAL_API_KEY and optional SMOKE_VIDEO_URL / SMOKE_AUDIO_URL
    from environment variables or .env.
  - Defaults API base to http://localhost:9000 (current local orchestrator).

This script does not modify Salad container groups or test inputs; it only
submits jobs and waits for them to reach a terminal state.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests


def load_env_file(path: str = ".env") -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def get_required(env: Dict[str, str], key: str) -> str:
    val = os.environ.get(key) or env.get(key)
    if not val:
        raise SystemExit(f"Missing required config {key} (set in environment or .env)")
    return val


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-name", required=True, help="Logical name for this batch (e.g. batch450_1)")
    parser.add_argument("--count", type=int, required=True, help="Number of jobs to submit in this batch")
    parser.add_argument(
        "--api-base",
        default=os.environ.get("ORCHESTRATOR_API_BASE", "http://localhost:9000"),
        help="Base URL for the orchestrator API (default http://localhost:9000)",
    )
    args = parser.parse_args()

    if args.count <= 0:
        raise SystemExit("count must be > 0")

    file_env = load_env_file()
    internal_api_key = get_required(file_env, "INTERNAL_API_KEY")

    # For smoke tests we expect the caller to configure these to the
    # desired B2 (or other) test inputs. The API itself still accepts
    # any valid URL.
    video_url = os.environ.get("SMOKE_VIDEO_URL") or file_env.get("SMOKE_VIDEO_URL")
    audio_url = os.environ.get("SMOKE_AUDIO_URL") or file_env.get("SMOKE_AUDIO_URL")
    if not video_url or not audio_url:
        raise SystemExit(
            "SMOKE_VIDEO_URL and SMOKE_AUDIO_URL must be set for batch tests "
            "(in environment or .env)."
        )

    api_base = args.api_base.rstrip("/")

    session = requests.Session()
    session.headers.update({"X-Internal-API-Key": internal_api_key})

    # Optional quick probe of the orchestrator health before starting a long batch.
    try:
        r = session.get(f"{api_base}/health", timeout=10)
        r.raise_for_status()
    except Exception as exc:
        raise SystemExit(f"Orchestrator health check failed at {api_base}: {exc}")

    # Record batch start
    start_ts = time.time()
    start_iso = datetime.now(timezone.utc).isoformat()

    job_ids: List[str] = []
    for i in range(args.count):
        payload = {
            "video_url": video_url,
            "audio_url": audio_url,
            "aspect_ratio": "9:16",
            "resolution": "720p",
            "metadata": {
                "batch_name": args.batch_name,
                "batch_index": i,
            },
        }
        try:
            resp = session.post(f"{api_base}/v1/avatar/jobs", json=payload, timeout=15)
            resp.raise_for_status()
        except Exception as exc:
            raise SystemExit(f"Failed to submit job {i} in batch {args.batch_name}: {exc}")
        data = resp.json()
        job_ids.append(data["id"])

    # Poll until all jobs in this batch reach a terminal state.
    remaining = set(job_ids)
    terminal = {"succeeded", "failed"}

    status_counts: Dict[str, int] = {}
    poll_interval = 10

    while remaining:
        done: List[str] = []
        for job_id in list(remaining):
            try:
                r = session.get(f"{api_base}/v1/avatar/jobs/{job_id}", timeout=10)
                if r.status_code != 200:
                    continue
                info = r.json()
            except Exception:
                continue
            st = (info.get("status") or "").lower()
            if st in terminal:
                done.append(job_id)
                status_counts[st] = status_counts.get(st, 0) + 1
        for job_id in done:
            remaining.discard(job_id)
        if remaining:
            time.sleep(poll_interval)

    end_ts = time.time()
    end_iso = datetime.now(timezone.utc).isoformat()
    wall_sec = end_ts - start_ts

    record = {
        "batch_name": args.batch_name,
        "count": args.count,
        "start_time": start_iso,
        "end_time": end_iso,
        "wall_time_sec": wall_sec,
        "status_counts": status_counts,
    }

    # Append to a simple JSONL log so we can compare batches later.
    log_path = "batch_wall_times.jsonl"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:
        print(f"WARNING: failed to write {log_path}: {exc}", file=sys.stderr)

    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()

