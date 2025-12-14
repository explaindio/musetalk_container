#!/usr/bin/env python3
import requests
import json
import time
import sys

API_KEY = 'd9cc20e0c3942018ca1fb72d6c9f857d89b7cfefdee3194a2f57c702a95608a4'
headers = {'Authorization': f'Bearer {API_KEY}'}

def get_instances():
    try:
        resp = requests.get('https://console.vast.ai/api/v0/instances', headers=headers, timeout=30)
        return resp.json()
    except Exception as e:
        print(f"Error: {e}")
        return None

def get_logs(instance_id):
    try:
        resp = requests.get(f'https://console.vast.ai/api/v0/instances/{instance_id}/logs', headers=headers, timeout=30)
        return resp.text
    except Exception as e:
        print(f"Error getting logs: {e}")
        return None

def destroy_instance(instance_id):
    try:
        resp = requests.delete(f'https://console.vast.ai/api/v0/instances/{instance_id}/', headers=headers, timeout=30)
        return resp.json()
    except Exception as e:
        print(f"Error destroying: {e}")
        return None

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    
    if cmd == "status":
        data = get_instances()
        if data and data.get('instances'):
            inst = data['instances'][0]
            print(f"Instance ID: {inst.get('id')}")
            print(f"Status: {inst.get('actual_status')}")
            print(f"GPU: {inst.get('gpu_name')}")
            print(f"SSH: ssh -p {inst.get('ssh_port')} root@{inst.get('ssh_host')}")
        else:
            print("No instances or error")
            print(json.dumps(data, indent=2) if data else "None")
    
    elif cmd == "logs":
        data = get_instances()
        if data and data.get('instances'):
            inst_id = data['instances'][0].get('id')
            logs = get_logs(inst_id)
            print(logs[:5000] if logs else "No logs")
    
    elif cmd == "destroy":
        data = get_instances()
        if data and data.get('instances'):
            inst_id = data['instances'][0].get('id')
            result = destroy_instance(inst_id)
            print(f"Destroyed: {result}")
