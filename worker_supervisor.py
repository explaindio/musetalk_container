#!/usr/bin/env python3
"""
Supervisor script for "Push" model workers (Vast.ai, etc.)

This script:
1. Starts the MuseTalk API (uvicorn) in the background
2. Runs a heartbeat/job-claiming loop in the foreground
3. Proxies claimed jobs to the local API
"""
import time
import requests
import subprocess
import os
import signal
import sys

# Configuration
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_BASE_URL", "https://orch.avatargen.online")
INTERNAL_KEY = os.environ.get("INTERNAL_API_KEY")
# Auto-detect ID from Hostname (Vast sets specific hostnames) or Env Var
WORKER_ID = os.environ.get("WORKER_ID", os.environ.get("HOSTNAME", "unknown-worker"))
GPU_CLASS = os.environ.get("GPU_CLASS", "Unknown_GPU")

def log(msg):
    print(f"[Supervisor] {msg}", flush=True)

if not INTERNAL_KEY:
    log("FATAL: INTERNAL_API_KEY not set.")
    sys.exit(1)

# 1. Start the Main App (Uvicorn)
log("Starting MuseTalk API (Uvicorn)...")
# Adjust this command to match your actual startup command
app_process = subprocess.Popen(
    ["uvicorn", "worker_app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    stdout=sys.stdout,
    stderr=sys.stderr
)

# Wait for App to be ready
log("Waiting for App to initialize...")
time.sleep(10) 

def heartbeat_loop():
    while True:
        # Check if App died
        if app_process.poll() is not None:
            log("CRITICAL: Main App died! Exiting wrapper.")
            sys.exit(1)

        # A. Heartbeat
        try:
            requests.post(
                f"{ORCHESTRATOR_URL}/internal/buffer/workers/{WORKER_ID}/heartbeat",
                headers={"X-Internal-Api-Key": INTERNAL_KEY},
                json={"status": "idle", "gpu_class": GPU_CLASS},
                timeout=5
            )
        except Exception as e:
            log(f"Heartbeat failed: {e}")

        # B. Claim Job
        try:
            r = requests.post(
                f"{ORCHESTRATOR_URL}/internal/buffer/jobs/claim",
                headers={"X-Internal-Api-Key": INTERNAL_KEY},
                json={"worker_id": WORKER_ID},
                timeout=5
            )
            
            if r.status_code == 200:
                data = r.json()
                if data.get("job"):
                    job = data["job"]
                    log(f"Claimed Job: {job['musetalk_job_id']}")
                    
                    # C. Process Job (Proxy to Localhost App)
                    # We send the job payload to our own local API
                    t0 = time.time()
                    try:
                        # Assuming your worker_app has a /generate endpoint
                        proc_res = requests.post(
                            "http://127.0.0.1:8000/generate",
                            json={
                                "musetalk_job_id": job["musetalk_job_id"],
                                "video_url": job["video_url"],
                                "audio_url": job["audio_url"],
                                "aspect_ratio": job["aspect_ratio"],
                                "resolution": job["resolution"]
                            },
                            timeout=600 
                        )
                        duration = time.time() - t0
                        log(f"Job Finished in {duration:.2f}s. Status: {proc_res.status_code}")
                    except Exception as err:
                        log(f"Processing Error: {err}")
                        
        except Exception as e:
            log(f"Claim Loop Error: {e}")

        time.sleep(2)

def signal_handler(signum, frame):
    log(f"Received signal {signum}. Shutting down...")
    app_process.terminate()
    try:
        app_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        log("App did not terminate gracefully, killing...")
        app_process.kill()
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

try:
    heartbeat_loop()
except KeyboardInterrupt:
    log("Stopping...")
    app_process.terminate()
