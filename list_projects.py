from salad_cloud_sdk import SaladCloudSdk
import json

API_KEY = "salad_cloud_user_V3FL969HSJKYR990jjBNDzUej7oZNEEmfCWuu6SSPuJ1jiY4p"
ORG_NAME = "explaindiolls"

sdk = SaladCloudSdk(api_key=API_KEY)

try:
    result = sdk.projects.list_projects(organization_name=ORG_NAME)
    print(f"Projects: {json.dumps(result.to_dict() if hasattr(result, 'to_dict') else str(result), indent=2)}")
except Exception as e:
    print(f"Error listing projects: {e}")
