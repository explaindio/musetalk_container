import requests
import json
import base64

# Extracted from config.json
AUTH_B64 = "ZXhwbGFpbmRpbzpkY2tyX3BhdF8yUE5MWFZJN3pFdjJwNm1tNFZDRUVsV1BpU00="
username, password = base64.b64decode(AUTH_B64).decode('utf-8').split(':')

def get_token(repo):
    url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull"
    try:
        r = requests.get(url, auth=(username, password))
        r.raise_for_status()
        return r.json()['token']
    except Exception as e:
        print(f"Error getting token for {repo}: {e}")
        return None

def list_tags(repo):
    token = get_token(repo)
    if not token:
        return

    url = f"https://registry-1.docker.io/v2/{repo}/tags/list"
    headers = {
        "Authorization": f"Bearer {token}"
    }
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        data = r.json()
        print(f"--- {repo} ---")
        if 'tags' in data:
            for tag in data['tags']:
                print(tag)
        else:
            print("No tags found or different response format.")
            print(data)
    except Exception as e:
        print(f"Error listing {repo}: {e}")

list_tags("explaindio/musetalk-worker")
list_tags("explaindio/musetalk-queue-worker")
