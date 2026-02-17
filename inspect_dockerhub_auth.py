from salad_cloud_sdk.models import ContainerRegistryAuthenticationDockerHub
import inspect

print("ContainerRegistryAuthenticationDockerHub signature:")
print(inspect.signature(ContainerRegistryAuthenticationDockerHub.__init__))

print("\nAttributes:")
for attr in dir(ContainerRegistryAuthenticationDockerHub):
    if not attr.startswith('_'):
        print(f"  {attr}")
