"""
pytdx 数据验证脚本
验证内容：
1. pytdx能获取哪些字段（实时快照 + 历史K线）
2. PE/PB/市值等核心字段是否有值
3. 和Tushare/akshare已知数据对比准确性
"""
import sys

try:
    from pytdx.hq import TdxHq_API
except ImportError:
    print("pytdx未安装，请执行: pip install pytdx")
    sys.exit(1)

import datetime

# ============================================================
# 连接通达信服务器
# ============================================================
def connect():
    api = TdxHq_API()
    # 常用通达信行情主站
    hosts = [
        ('119.147.212.81', 7709),
        ('112.74.214.43', 7709),
        ('221.231.141.60', 7709),
        ('101.129.218.222', 7709),
        ('14.215.128.18', 7709),
        ('47.103.48.53', 7709),
        ('218.75.126.9', 7709),
        ('115.238.56.198', 7709),
        ('124.160.88.183', 7709),
        ('60.12.136.250', 7709),
        ('218.108.98.244', 7709),
        ('218.108.47.69', 7709),
        ('180.153.18.170', 7709),
        ('180.153.18.171', 7709),
        ('202.108.98.247', 7709),
    ]
    for ip, port in hosts:
        try:
            if api.connect(ip, port):
                print(f"连接成功: {ip}:{port}")
                return api
        except Exception as e:
            print(f"连接失败 {ip}:{port}: {e}")
    raise RuntimeError("所有通达信服务器连接失败")

# ============================================================
# 股票代码转换: ts_code -> (market, code)
# ============================================================
def ts_to_pytdx(ts_code):
    """600000.SH -> (1, '600000')  000001.SZ -> (0, '000001')"""
    code, market = ts_code.split(".")
    if market == "SH":
        return 1, code
    elif market == "SZ":
        return 0, code
    return None, None

# ============================================================
# 验证1: 实时快照字段
# ============================================================
def test_realtime_quotes(api):
    print("\n" + "="*60)
    print("验证1: 实时快照字段 (get_security_quotes)")
    print("="*60)
    
    # 测试几只代表性股票
    test_stocks = [
        "600000.SH",  # 浦发银行
        "000001.SZ",  # 平安银行
        "600519.SH",  # 贵州茅台
        "000858.SZ",  # 五粮液
        "601318.SH",  # 中国平安
    ]
    
    req_list = []
    for ts_code in test_stocks:
        market, code = ts_to_pytdx(ts_code)
        if market is not None:
            req_list.append((market, code))
    
    df = api.get_security_quotes(req_list)
    if df is None or (hasattr(df, '__len__') and len(df) == 0):
        print("ERROR: 获取实时快照失败")
        return
    
    print(f"\n获取到 {len(df)} 只股票数据")
    
    # 打印字段列表
    if hasattr(df, 'columns'):
        print(f"\n可用字段: {list(df.columns)}")
    else:
        # 返回的是list of dict
        if len(df) > 0:
            print(f"\n可用字段: {list(df[0].keys())}")
    
    # 打印每只股票的详细数据
    for i, row in enumerate(df):
        if hasattr(row, 'to_dict'):
            d = row.to_dict()
        else:
            d = row
        print(f"\n--- {test_stocks[i]} ---")
        for k, v in d.items():
            print(f"  {k}: {v}")

# ============================================================
# 验证2: 扩展数据 (含PE/PB/总股本等)
# ============================================================
def test_extended_data(api):
    print("\n" + "="*60)
    print("验证2: 扩展行情数据 (get_security_quotes 扩展字段)")
    print("="*60)
    
    # pytdx的get_security_quotes返回的字段中可能包含：
    # price, last_close, open, high, low, pre_close
    # vol, amount
    # 检查是否有 PE, PB, 总市值, 流通市值 等字段
    
    market, code = ts_to_pytdx("600519.SH")  # 茅台
    df = api.get_security_quotes([(market, code)])
    if df is None or len(df) == 0:
        print("ERROR: 获取扩展数据失败")
        return
    
    row = df[0] if isinstance(df, list) else df.iloc[0]
    if hasattr(row, 'to_dict'):
        row = row.to_dict()
    
    # 检查关键字段
    key_fields = ['price', 'last_close', 'open', 'high', 'low', 
                  'vol', 'amount', 'pre_close',
                  'pe', 'pb', 'mktcap', 'volratio',
                  'liutongguben', 'zongguben', 'huanshoulv']
    
    print("\n关键字段检查:")
    for f in key_fields:
        val = row.get(f, "字段不存在")
        status = "✅" if val != "字段不存在" and val is not None and val != 0 else "❌"
        print(f"  {status} {f}: {val}")

# ============================================================
# 验证3: 和Tushare数据对比准确性
# ============================================================
def test_accuracy(api):
    print("\n" + "="*60)
    print("验证3: 数据准确性对比 (pytdx vs Tushare)")
    print("="*60)
    
    # 用浦发银行(600000.SH)做对比
    # Tushare已知数据(手动填写一个近期交易日的参考值)
    # 注意：这些值需要你根据Tushare查询结果手动更新
    tushare_ref = {
        "600000.SH": {"name": "浦发银行", "pe_ref": None, "pb_ref": None},
        "600519.SH": {"name": "贵州茅台", "pe_ref": None, "pb_ref": None},
    }
    
    # 获取pytdx实时数据
    stocks = ["600000.SH", "600519.SH"]
    req_list = []
    for ts in stocks:
        m, c = ts_to_pytdx(ts)
        if m is not None:
            req_list.append((m, c))
    
    df = api.get_security_quotes(req_list)
    if df is None:
        print("ERROR: 获取对比数据失败")
        return
    
    for i, ts in enumerate(stocks):
        row = df[i] if isinstance(df, list) else df.iloc[i]
        if hasattr(row, 'to_dict'):
            row = row.to_dict()
        
        print(f"\n--- {ts} {tushare_ref[ts]['name']} ---")
        print(f"  pytdx price: {row.get('price')}")
        print(f"  pytdx open:  {row.get('open')}")
        print(f"  pytdx high:  {row.get('high')}")
        print(f"  pytdx low:   {row.get('low')}")
        print(f"  pytdx vol:   {row.get('vol')} (手)")
        print(f"  pytdx amount:{row.get('amount')} (元)")
        print(f"  pytdx PE:    {row.get('pe', '无此字段')}")
        print(f"  pytdx PB:    {row.get('pb', '无此字段')}")
    
    print("\n⚠️  请手动将以上价格/成交量与东方财富/同花顺实时行情对比")
    print("    如果价格/成交量一致，说明pytdx数据源准确")

# ============================================================
# 验证4: 历史K线数据
# ============================================================
def test_history_kline(api):
    print("\n" + "="*60)
    print("验证4: 历史K线数据 (get_security_bars)")
    print("="*60)
    
    market, code = ts_to_pytdx("600000.SH")
    # 获取最近5天日K线
    df = api.get_security_bars(9, market, code, 0, 5)  # 9=日线
    if df is None or len(df) == 0:
        print("ERROR: 获取历史K线失败")
        return
    
    print(f"\n获取到 {len(df)} 根K线")
    if hasattr(df, 'columns'):
        print(f"可用字段: {list(df.columns)}")
    
    for i, row in enumerate(df):
        if hasattr(row, 'to_dict'):
            d = row.to_dict()
        else:
            d = row
        print(f"\n  K线 {i+1}:")
        for k, v in d.items():
            print(f"    {k}: {v}")
    
    print("\n⚠️  历史K线中不包含PE/PB/市值字段")
    print("    pytdx历史数据只有: open/close/high/low/vol/amount")
    print("    PE/PB/市值需要从实时快照获取，或通过其他接口计算")

# ============================================================
# 验证5: 批量获取速度测试
# ============================================================
def test_batch_speed(api):
    print("\n" + "="*60)
    print("验证5: 批量获取速度测试")
    print("="*60)
    
    import time
    
    # 获取全部股票列表
    print("\n获取沪深A股列表...")
    sh_stocks = api.get_security_list(1, 0)  # 上海
    sz_stocks = api.get_security_list(0, 0)  # 深圳
    
    total_sh = len(sh_stocks) if sh_stocks else 0
    total_sz = len(sz_stocks) if sz_stocks else 0
    print(f"上海: {total_sh} 只, 深圳: {total_sz} 只")
    
    # 批量获取实时行情(最多800只/次)
    all_req = []
    if sh_stocks:
        for s in sh_stocks[:400]:
            all_req.append((1, s['code']))
    if sz_stocks:
        for s in sz_stocks[:400]:
            all_req.append((0, s['code']))
    
    print(f"\n测试批量获取 {len(all_req)} 只...")
    start = time.time()
    df = api.get_security_quotes(all_req)
    elapsed = time.time() - start
    
    if df is not None:
        print(f"获取 {len(df)} 只, 耗时 {elapsed:.2f} 秒")
        print(f"速度: {len(df)/elapsed:.0f} 只/秒")
    else:
        print("获取失败")

# ============================================================
# 主函数
# ============================================================
def main():
    print("pytdx 数据验证脚本")
    print("="*60)
    
    api = connect()
    
    try:
        test_realtime_quotes(api)
        test_extended_data(api)
        test_accuracy(api)
        test_history_kline(api)
        test_batch_speed(api)
    finally:
        api.disconnect()
        print("\n连接已断开")

if __name__ == "__main__":
    main()
