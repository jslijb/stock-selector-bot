import requests
import json

url = "https://push2.eastmoney.com/api/qt/clist/get"
params = {
    "pn": 1,
    "pz": 6000,
    "po": 1,
    "np": 1,
    "ut": "bd1d9ddb04089700cf9c05778a8bda30",
    "fltt": 2,
    "invt": 2,
    "fid": "f3",
    "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
    "fields": "f2,f12,f14,f20,f21",
}
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

resp = requests.get(url, params=params, headers=headers, timeout=30)
data = resp.json()
items = data.get("data", {}).get("diff", [])
total = data.get("data", {}).get("total", 0)
print(f"API返回 total={total}, 实际items={len(items)}")

# 检查000001是否在
codes = [str(item.get("f12", "")).zfill(6) for item in items]
if "000001" in codes:
    print("000001 在列表中")
else:
    print("000001 不在列表中!")

# 看000001附近
for item in items[:5]:
    print(f"  {item.get('f12', '')} {item.get('f14', '')} close={item.get('f2', '')} total_mv={item.get('f20', '')}")
