#!/usr/bin/env python3
"""
Salad Cloud FastWan Worker Test Script - Using SDK
"""
from salad_cloud_sdk import SaladCloudSdk, Environment
import json
import time

API_KEY = "salad_cloud_user_V3FL969HSJKYR990jjBNDzUej7oZNEEmfCWuu6SSPuJ1jiY4p"
ORG_NAME = "explaindiolls"
PROJECT_NAME = "project2"

# Initialize SDK
sdk = SaladCloudSdk(
    api_key=API_KEY,
    timeout=60000
)

print("=" * 70)
print("SALAD CLOUD FASTWAN WORKER TEST (SDK)")
print("=" * 70)
print()

# List container groups
print("Step 1: List container groups...")
print("-" * 70)
try:
    result = sdk.container_groups.list_container_groups(
        organization_name=ORG_NAME,
        project_name=PROJECT_NAME
    )
    print(f"Container Groups: {json.dumps(result.to_dict() if hasattr(result, 'to_dict') else str(result), indent=2)}")
except Exception as e:
    print(f"Error listing container groups: {e}")
print()

# List queues
print("Step 2: List queues...")
print("-" * 70)
try:
    result = sdk.queues.list_queues(
        organization_name=ORG_NAME,
        project_name=PROJECT_NAME
    )
    print(f"Queues: {json.dumps(result.to_dict() if hasattr(result, 'to_dict') else str(result), indent=2)}")
except Exception as e:
    print(f"Error listing queues: {e}")
print()

print("SDK initialized successfully!")
print(f"Organization: {ORG_NAME}")
print(f"Project: {PROJECT_NAME}")
