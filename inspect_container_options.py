from salad_cloud_sdk import SaladCloudSdk
import salad_cloud_sdk.models as models

print("Available models:")
print([x for x in dir(models) if not x.startswith('_')])
