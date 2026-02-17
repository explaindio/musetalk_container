from salad_cloud_sdk import SaladCloudSdk
import json

API_KEY = "salad_cloud_user_V3FL969HSJKYR990jjBNDzUej7oZNEEmfCWuu6SSPuJ1jiY4p"
sdk = SaladCloudSdk(api_key=API_KEY)

try:
    print(dir(sdk.organization_data))
except Exception as e:
    print(f"Error: {e}")
