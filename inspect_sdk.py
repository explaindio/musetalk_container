from salad_cloud_sdk import SaladCloudSdk
import json

API_KEY = "salad_cloud_user_V3FL969HSJKYR990jjBNDzUej7oZNEEmfCWuu6SSPuJ1jiY4p"
sdk = SaladCloudSdk(api_key=API_KEY)

print(dir(sdk))
try:
    print(dir(sdk.container_groups))
except:
    pass
