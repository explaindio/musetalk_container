#!/usr/bin/env python3
"""
MuseTalk Unified Polling Worker

A provider-agnostic worker that polls the orchestrator for jobs.
Works with: Salad, OctaSpace, Vast.ai, TensorDock, Runpod, or any GPU provider.

See UNIFIED_WORKER_SPEC.md for full specification.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
import threading
import httpx
import psutil
import speedtest
import platform
import math
from typing import Any, Dict, Optional

# ==============================================================================
# Configuration from Environment Variables
# ==============================================================================

ORCH_URL = os.environ.get("ORCHESTRATOR_BASE_URL", "https://orch.avatargen.online")
API_KEY = os.environ.get("INTERNAL_API_KEY", "")

# Auto-detect worker ID from provider-specific env vars
WORKER_ID = (
    os.environ.get("SALAD_MACHINE_ID") or
    os.environ.get("VAST_CONTAINERLABEL") or
    os.environ.get("OCTASPACE_NODE_ID") or
    os.environ.get("WORKER_ID") or
    f"worker-{os.urandom(4).hex()}"
)

WORKER_TYPE = os.environ.get("WORKER_TYPE", "main")  # main, transient, expensive
PROVIDER = os.environ.get("PROVIDER", "unknown")  # salad, octaspace, vast, tensordock, runpod
GPU_CLASS = os.environ.get("GPU_CLASS_NAME", "unknown")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SEC", "5"))

# B2 Upload config (if needed directly, though currently handled by /generate)
B2_KEY_ID = os.environ.get("B2_KEY_ID", "")
B2_APP_KEY = os.environ.get("B2_APP_KEY", "")
B2_BUCKET_NAME = os.environ.get("B2_BUCKET_NAME", "")
B2_PREFIX = os.environ.get("B2_PREFIX", "")

HEADERS = {"X-Internal-API-Key": API_KEY, "Content-Type": "application/json"}

# Global system info cache
SYSTEM_METRICS = {}

# Global state for heartbeat thread
WORKER_STATE = {
    "status": "idle",
    "current_job_id": None
}
STATE_LOCK = threading.Lock()

# ==============================================================================
# Heartbeat Thread
# ==============================================================================

def get_system_metrics():
    """
    Collects system metrics once on startup.
    Includes: CPU, RAM, Disk, and Download Speed.
    """
    print("[system] Collecting system metrics...", flush=True)
    metrics = {
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "cpu_cores_logical": psutil.cpu_count(logical=True),
        "cpu_model": platform.processor(),
    }

    try:
        mem = psutil.virtual_memory()
        metrics["ram_total_gb"] = round(mem.total / (1024**3), 2)
        metrics["ram_available_gb"] = round(mem.available / (1024**3), 2)
    except Exception as e:
        print(f"[system] Failed to get RAM info: {e}", flush=True)

    try:
        disk = psutil.disk_usage('/')
        metrics["disk_total_gb"] = round(disk.total / (1024**3), 2)
        metrics["disk_free_gb"] = round(disk.free / (1024**3), 2)
    except Exception as e:
        print(f"[system] Failed to get Disk info: {e}", flush=True)
        
    try:
        print("[system] Running download speed test (this may take 10-20s)...", flush=True)
        st = speedtest.Speedtest()
        st.get_best_server()
        download_speed = st.download() / 1_000_000  # Mbps
        metrics["download_speed_mbps"] = round(download_speed, 2)
        print(f"[system] Download speed: {metrics['download_speed_mbps']} Mbps", flush=True)
    except Exception as e:
        print(f"[system] Speedtest failed: {e}", flush=True)
        metrics["download_speed_mbps"] = None

    return metrics

def heartbeat_loop():
    """
    Background thread that sends heartbeats every 5 seconds.
    Ensures the worker stays 'online' even when blocking on inference.
    """
    print(f"[heartbeat] Thread started for {WORKER_ID}", flush=True)
    
    while True:
        try:
            # Recreate client on connection errors
            with httpx.Client(timeout=10.0, http2=False) as client:
                while True:
                    try:
                        # Read current state
                        with STATE_LOCK:
                            current_status = WORKER_STATE["status"]
                            current_job = WORKER_STATE["current_job_id"]

                        # Send heartbeat
                        resp = client.post(
                            f"{ORCH_URL}/internal/main/workers/{WORKER_ID}/heartbeat",
                            json={
                                "status": current_status,
                                "current_job_id": current_job,
                                "provider": PROVIDER,
                                "gpu_class": GPU_CLASS,
                                "worker_type": WORKER_TYPE,
                                "system_info": SYSTEM_METRICS,
                            },
                            headers=HEADERS
                        )
                        
                        if resp.status_code != 200:
                            print(f"[heartbeat] Warning: HTTP {resp.status_code} {resp.text[:100]}", flush=True)
                        
                        # Wait for next beat
                        time.sleep(5)
                        
                    except (httpx.RequestError, httpx.HTTPStatusError) as e:
                        print(f"[heartbeat] Network/SSL Error: {e}. Reconnecting...", flush=True)
                        break # Break inner loop to recreate client
                        
                    except Exception as e:
                        print(f"[heartbeat] Failed: {e}", flush=True)
                        time.sleep(5)
                        
        except Exception as e:
            print(f"[heartbeat] Critical outer loop error: {e}", flush=True)
            time.sleep(5)

# ==============================================================================
# API Calls (Main Thread)
# ==============================================================================

def claim_job(client: httpx.Client) -> Optional[Dict[str, Any]]:
    """
    Attempt to claim a job from the orchestrator.
    Uses retry with exponential backoff.
    """
    for attempt in range(3):
        try:
            resp = client.post(
                f"{ORCH_URL}/internal/main/jobs/claim",
                json={
                    "worker_id": WORKER_ID,
                    "worker_type": WORKER_TYPE,
                    "gpu_class": GPU_CLASS,
                },
                headers=HEADERS,
                timeout=15.0,
            )
            if resp.status_code != 200:
                print(f"[claim_job] HTTP {resp.status_code}: {resp.text}", flush=True)
                return None

            data = resp.json()
            if data.get("error"):
                print(f"[claim_job] Error: {data['error']}", flush=True)
                return None
            return data.get("job")

        except Exception as e:
            print(f"[claim_job] Attempt {attempt + 1} failed: {e}", flush=True)
            time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s

    return None


def report_progress(
    client: httpx.Client,
    job_id: str,
    status: str,
    progress: float,
    phase: str,
    metrics: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    output_url: Optional[str] = None,
) -> bool:
    """
    Report job progress to orchestrator using existing endpoint.
    """
    try:
        payload = {
            "status": status,
            "progress": progress,
            "phase": phase,
            "worker_id": WORKER_ID,
            "metrics": metrics,
            "error": error,
        }
        if output_url:
            payload["output_url"] = output_url

        resp = client.post(
            f"{ORCH_URL}/internal/jobs/{job_id}/progress",
            json=payload,
            headers=HEADERS,
            timeout=10.0,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[report_progress] Failed: {e}", flush=True)
        return False
        



# ==============================================================================
# Job Processing
# ==============================================================================

def process_job(client: httpx.Client, job: Dict[str, Any]) -> bool:
    """
    Process a claimed job by calling the local /generate endpoint.
    Returns True on success, False on failure.
    """
    job_id = job["musetalk_job_id"]
    print(f"[process_job] Starting job {job_id}", flush=True)

    try:
        # Report downloading phase
        report_progress(client, job_id, "running", 0.05, "downloading")

        # Call local /generate endpoint (same container, port 8000)
        gen_body = {
            "musetalk_job_id": job_id,
            "video_url": job["video_url"],
            "audio_url": job["audio_url"],
            "aspect_ratio": job.get("aspect_ratio", "1:1"),
            "resolution": job.get("resolution", "512x512"),
            "params": {},
        }

        # Long timeout for inference (10 minutes)
        # Heartbeat thread will keep us alive during this wait
        gen_resp = client.post(
            "http://localhost:8000/generate",
            json=gen_body,
            timeout=600.0,
        )

        if gen_resp.status_code == 200:
            result = gen_resp.json()
            print(f"[process_job] /generate response: {result}", flush=True)
            status = result.get("status")
            if status == "succeeded" or status == "success":
                print(f"[process_job] Job {job_id} succeeded", flush=True)
                
                # Report final success with output URL
                output_url = result.get("output_url")
                metrics = result.get("metrics")
                report_progress(client, job_id, "succeeded", 1.0, "completed", metrics=metrics, output_url=output_url)
                
                return True
            else:
                error_msg = result.get("error") or result.get("error_message") or "Unknown error from /generate"
                print(f"[process_job] Job {job_id} failed: {error_msg}", flush=True)
                report_progress(client, job_id, "failed", 0.0, "failed", error=error_msg)
                return False
        else:
            error_msg = f"HTTP {gen_resp.status_code}: {gen_resp.text[:200]}"
            print(f"[process_job] Job {job_id} HTTP error: {error_msg}", flush=True)
            report_progress(client, job_id, "failed", 0.0, "failed", error=error_msg)
            return False

    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"[process_job] Job {job_id} exception: {error_msg}", flush=True)
        print(traceback.format_exc(), flush=True)
        report_progress(client, job_id, "failed", 0.0, "failed", error=error_msg)
        return False


# ==============================================================================
# Main Loop
# ==============================================================================

def main():
    print("=" * 60, flush=True)
    print("MuseTalk Unified Polling Worker (Threaded Heartbeat)")
    print("=" * 60, flush=True)
    print(f"Worker ID:    {WORKER_ID}", flush=True)
    print(f"Worker Type:  {WORKER_TYPE}", flush=True)
    print(f"Provider:     {PROVIDER}", flush=True)
    print(f"GPU Class:    {GPU_CLASS}", flush=True)
    print(f"Orchestrator: {ORCH_URL}", flush=True)
    print(f"Poll Interval: {POLL_INTERVAL}s", flush=True)
    print("=" * 60, flush=True)

    if not API_KEY:
        print("[FATAL] INTERNAL_API_KEY not set!", flush=True)
        sys.exit(1)

    # Collect system metrics before starting
    global SYSTEM_METRICS
    SYSTEM_METRICS = get_system_metrics()

    # Start heartbeat thread
    hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    hb_thread.start()

    while True:
        try:
            # Recreate client on errors to clear bad SSL states
            with httpx.Client(http2=False, timeout=30.0) as client:
                while True:
                    try:
                        # 1. Try to claim a job
                        job = claim_job(client)

                        if job:
                            job_id = job["musetalk_job_id"]
                            print(f"[main] Claimed job: {job_id}", flush=True)

                            # Update state to Busy (heartbeat thread picks this up)
                            with STATE_LOCK:
                                WORKER_STATE["status"] = "busy"
                                WORKER_STATE["current_job_id"] = job_id

                            # Process the job (blocking)
                            process_job(client, job)

                            print(f"[main] Finished job: {job_id}", flush=True)

                            # Reset state to Idle
                            with STATE_LOCK:
                                WORKER_STATE["status"] = "idle"
                                WORKER_STATE["current_job_id"] = None

                        else:
                            # No job available
                            with STATE_LOCK:
                                # Ensure we are idle if we were somehow stuck
                                if WORKER_STATE["status"] != "idle":
                                    WORKER_STATE["status"] = "idle"
                                    WORKER_STATE["current_job_id"] = None
                            
                            time.sleep(POLL_INTERVAL)

                    except (httpx.RequestError, httpx.HTTPStatusError) as e:
                        print(f"[main] Network/SSL Error in loop: {e}. Reconnecting client...", flush=True)
                        break  # Break inner loop to recreate client
                    
                    except KeyboardInterrupt:
                        raise  # Let outer loop handle it (or just exit)

        except KeyboardInterrupt:
            print("\n[main] Shutting down...", flush=True)
            break
        except Exception as e:
            print(f"[main] Unexpected error in outer loop: {e}", flush=True)
            print(traceback.format_exc(), flush=True)
            
            # Reset state on error
            with STATE_LOCK:
                WORKER_STATE["status"] = "idle"
                WORKER_STATE["current_job_id"] = None
                
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
