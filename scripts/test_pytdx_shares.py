from pytdx.hq import TdxHq_API

api = TdxHq_API()
if api.connect('119.147.212.81', 7709):
    # 测试 get_financial_info
    print("=== get_financial_info (600000) ===")
    try:
        data = api.get_financial_info(1, 0)
        if data:
            print(f"类型: {type(data)}")
            if isinstance(data, dict):
                for k, v in data.items():
                    print(f"  {k}: {v}")
            elif isinstance(data, list):
                print(f"行数: {len(data)}")
                if data:
                    print(f"第一行: {data[0]}")
    except Exception as e:
        print(f"异常: {e}")

    # 测试 get_security_list
    print("\n=== get_security_list (前10只) ===")
    try:
        stocks = api.get_security_list(1, 0)
        if stocks:
            print(f"行数: {len(stocks)}")
            if stocks:
                print(f"字段: {stocks[0].keys() if isinstance(stocks[0], dict) else stocks[0]}")
                for s in stocks[:5]:
                    print(f"  {s}")
    except Exception as e:
        print(f"异常: {e}")

    api.disconnect()
else:
    print("连接失败")
