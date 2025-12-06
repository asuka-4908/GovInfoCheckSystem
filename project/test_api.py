import requests
import json

api_key = "qbvOGz9XSuLh7MF3rP7"
song = "稻香"
music_url = "https://api.yaohud.cn/api/music/kuwo"

print(f"\n--- Debug Verification: GET msg={song}&n=1 ---")
params = {
    'key': api_key,
    'msg': song,
    'n': 1
}

try:
    resp = requests.get(music_url, params=params)
    print(f"Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
except Exception as e:
    print(f"Exception: {e}")
