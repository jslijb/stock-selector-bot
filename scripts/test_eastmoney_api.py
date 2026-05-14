import requests
import json

url = "https://push2.eastmoney.com/api/qt/clist/get"
params = {
    "pn": 1,
    "pz": 10,
    "po": 1,
    "np": 1,
    "ut": "bd1d9ddb04089700cf9c05778a8bda30",
    "fltt": 2,
    "invt": 2,
    "fid": "f3",
    "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
    "fields": "f2,f3,f5,f6,f9,f12,f14,f20,f21,f23",
}
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

resp = requests.get(url, params=params, headers=headers, timeout=30)
print(f"status: {resp.status_code}")
data = resp.json()
items = data.get("data", {}).get("diff", [])
print(f"items count: {len(items)}")
if items:
    print(f"fields sample: {items[0]}")
    for item in items[:3]:
        code = item.get("f12", "")
        name = item.get("f14", "")
        close = item.get("f2", "")
        total_mv = item.get("f20", "")
        circ_mv = item.get("f21", "")
        pe = item.get("f9", "")
        pb = item.get("f23", "")
        turnover = item.get("f5", "")
        print(f"  {code} {name}: close={close}, total_mv={total_mv}, circ_mv={circ_mv}, PE={pe}, PB={pb}, turnover={turnover}")
        if close and total_mv and float(close) > 0:
            total_share = float(total_mv) / float(close) / 10000.0
            circ_share = float(circ_mv) / float(close) / 10000.0 if circ_mv else 0
            print(f"    -> total_share={total_share:.2f}万股, circ_share={circ_share:.2f}万股")
