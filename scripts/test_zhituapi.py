import os
import requests
import json

token = os.environ.get("ZHIMIAN_TOKEN")
if not token:
    print("环境变量 ZHIMIAN_TOKEN 未设置!")
    exit(1)

print(f"token: {token[:8]}...")

url = f"https://api.zhituapi.com/hs/real/zbjy/600000?token={token}"
print(f"\n请求: {url}")

try:
    resp = requests.get(url, timeout=15)
    print(f"status: {resp.status_code}")
    data = resp.json()
    print(f"type: {type(data)}")
    
    if isinstance(data, list):
        print(f"总条数: {len(data)}")
        if data:
            print(f"\n第一条: {json.dumps(data[0], ensure_ascii=False, indent=2)}")
            print(f"\n最后一条: {json.dumps(data[-1], ensure_ascii=False, indent=2)}")
            print(f"\n所有字段: {list(data[0].keys())}")
    elif isinstance(data, dict):
        print(f"keys: {list(data.keys())}")
        print(f"body: {json.dumps(data, ensure_ascii=False, indent=2)[:3000]}")
    else:
        print(f"body: {str(data)[:3000]}")
except Exception as e:
    print(f"异常: {e}")
    import traceback
    traceback.print_exc()
