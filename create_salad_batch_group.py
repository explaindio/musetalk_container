#!/usr/bin/env python3
"""
Create a test batch-priority container group on SaladCloud.
"""
import os
import sys
import json
import requests
from typing import Dict, Any, Optional

# --- Configuration ---
# RTX 3090 (24 GB)
GPU_ID = "a5db5c50-cbcb-4596-ae80-6a0c8090d80f"
GPU_NAME = "RTX 3090"
IMAGE = "explaindio/musetalk-worker:unified-v1"
GROUP_NAME = "musetalk-batch-test-3090"
API_BASE = "https://api.salad.com/api/public"

def load_env_file(path: str = ".env") -> Dict[str, str]:
    """Minimal .env parser."""
    env: Dict[str, str] = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env

def get_config() -> Dict[str, str]:
    file_env = load_env_file()
    cfg = {}
    
    for key in ["SALAD_API_KEY", "SALAD_ORG_NAME", "SALAD_PROJECT_NAME"]:
        val = os.environ.get(key) or file_env.get(key)
        if not val:
            print(f"Error: Missing {key} in environment or .env")
            sys.exit(1)
        cfg[key] = val
    return cfg

def create_batch_group(cfg: Dict[str, str]):
    url = f"{API_BASE}/organizations/{cfg['SALAD_ORG_NAME']}/projects/{cfg['SALAD_PROJECT_NAME']}/containers"
    
    headers = {
        "Salad-Api-Key": cfg["SALAD_API_KEY"],
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Environment variables for the worker
    # Note: These are minimal for a test group creation check.
    # In a real deployment, we'd add all the env vars from deployment_info.md
    env_vars = {
        "WORKER_TYPE": "test-batch",
        "PROVIDER": "salad",
        "GPU_CLASS_NAME": "RTX-3090-Batch",
        "POLL_INTERVAL_SEC": "10",
        "BATCH_SIZE": "8"
    }

    payload = {
        "name": GROUP_NAME,
        "display_name": f"{GPU_NAME} Batch Test",
        "container": {
            "image": IMAGE,
            "resources": {
                "cpu": 4,
                "memory": 12288, # 12 GB RAM
                "gpu_classes": [GPU_ID]
            },
            "priority": "batch", # CRITICAL: This sets the batch priority
            "environment_variables": env_vars,
            "command": [], # Use default entrypoint
        },
        "replicas": 1,
        "restart_policy": "always", # or "never" for one-off
        "autostart_policy": False # Don't start immediately, just create config
    }

    print(f"Creating container group '{GROUP_NAME}' with batch priority...")
    print(f"Image: {IMAGE}")
    print(f"GPU: {GPU_NAME} ({GPU_ID})")
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if resp.status_code == 201:
            print("\nSUCCESS: Container Group Created!")
            data = resp.json()
            print(f"ID: {data.get('id')}")
            print(f"Name: {data.get('name')}")
            print(f"Status: {data.get('current_state', {}).get('status')}")
            print("Note: autostart_policy is False. Go to Salad portal to start it if desired.")
        elif resp.status_code == 409:
            print(f"\nExample group '{GROUP_NAME}' already exists.")
            print("Delete it first if you want to recreate it.")
        else:
            print(f"\nFAILED: {resp.status_code}")
            print(resp.text)
            
    except Exception as e:
        print(f"\nError creating group: {e}")

if __name__ == "__main__":
    cfg = get_config()
    create_batch_group(cfg)
