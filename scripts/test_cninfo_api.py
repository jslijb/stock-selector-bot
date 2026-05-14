import requests
import json

# 巨潮资讯 p_stock2215 股本结构接口
url = "http://webapi.cninfo.com.cn/api/stock/p_stock2215"

# 测试1: 不带参数
print("=== 测试1: 无参数 ===")
try:
    resp = requests.get(url, timeout=15)
    print(f"status: {resp.status_code}")
    print(f"headers content-type: {resp.headers.get('content-type', '')}")
    text = resp.text[:2000]
    print(f"body: {text}")
except Exception as e:
    print(f"异常: {e}")

# 测试2: 带证券代码参数
print("\n=== 测试2: 600000 ===")
try:
    params = {"scode": "600000"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "http://www.cninfo.com.cn/",
        "Accept": "application/json",
    }
    resp = requests.get(url, params=params, headers=headers, timeout=15)
    print(f"status: {resp.status_code}")
    text = resp.text[:3000]
    print(f"body: {text}")
except Exception as e:
    print(f"异常: {e}")

# 测试3: POST方式
print("\n=== 测试3: POST 600000 ===")
try:
    data = {"scodes": "600000"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "http://www.cninfo.com.cn/",
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    resp = requests.post(url, data=data, headers=headers, timeout=15)
    print(f"status: {resp.status_code}")
    text = resp.text[:3000]
    print(f"body: {text}")
except Exception as e:
    print(f"异常: {e}")
