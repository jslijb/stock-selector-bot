"""
pytdx vs Tushare 数据准确性对比
从DuckDB读取Tushare已知数据，与pytdx历史K线对比
"""
import sys
sys.path.insert(0, 'D:/Python/agent_a_sk')

from pytdx.hq import TdxHq_API
from src.data.db import Database
from src.data.schema import init_schema
from loguru import logger
import datetime

def connect_pytdx():
    api = TdxHq_API()
    hosts = [
        ('218.75.126.9', 7709),
        ('119.147.212.81', 7709),
        ('221.231.141.60', 7709),
        ('101.129.218.222', 7709),
        ('14.215.128.18', 7709),
        ('115.238.56.198', 7709),
        ('124.160.88.183', 7709),
        ('60.12.136.250', 7709),
    ]
    for ip, port in hosts:
        try:
            if api.connect(ip, port):
                print(f"pytdx连接成功: {ip}:{port}")
                return api
        except Exception:
            pass
    raise RuntimeError("pytdx连接失败")

def ts_to_pytdx(ts_code):
    code, market = ts_code.split(".")
    return (1, code) if market == "SH" else (0, code)

def main():
    db = Database.get_instance('./data/stock_agent.duckdb')
    init_schema(db)
    api = connect_pytdx()

    test_stocks = {
        "600000.SH": "浦发银行",
        "000001.SZ": "平安银行",
        "600519.SH": "贵州茅台",
        "000858.SZ": "五粮液",
        "601318.SH": "中国平安",
        "000333.SZ": "美的集团",
        "600036.SH": "招商银行",
        "002415.SZ": "海康威视",
    }

    # 从DB取最近5个交易日的Tushare数据
    max_date = db.fetch_one("SELECT MAX(trade_date) FROM daily_price")[0]
    print(f"\nDB最新日期: {max_date}")

    all_pass = True
    for ts_code, name in test_stocks.items():
        print(f"\n{'='*60}")
        print(f"对比: {ts_code} {name}")
        print(f"{'='*60}")

        ts_df = db.fetch_df(
            """SELECT trade_date, open, close, high, low, vol, amount
            FROM daily_price WHERE ts_code = ?
            ORDER BY trade_date DESC LIMIT 5""",
            [ts_code],
        )
        if ts_df.empty:
            print("  DB中无数据，跳过")
            continue

        market, code = ts_to_pytdx(ts_code)
        pytdx_df = api.get_security_bars(9, market, code, 0, 10)
        if pytdx_df is None or len(pytdx_df) == 0:
            print("  pytdx无数据，跳过")
            continue

        for _, ts_row in ts_df.iterrows():
            td = ts_row["trade_date"]
            if hasattr(td, 'strftime'):
                td_str = td.strftime("%Y-%m-%d")
            else:
                td_str = str(td)[:10]

            pytdx_match = None
            for _, pr in pytdx_df.iterrows():
                pytdx_dt = f"{int(pr['year'])}-{int(pr['month']):02d}-{int(pr['day']):02d}"
                if pytdx_dt == td_str:
                    pytdx_match = pr
                    break

            if pytdx_match is None:
                print(f"  {td_str}: pytdx无此日K线")
                continue

            ts_close = float(ts_row["close"])
            pytdx_close = float(pytdx_match["close"])
            ts_vol = float(ts_row["vol"])
            pytdx_vol = float(pytdx_match["vol"])
            ts_amount = float(ts_row["amount"])
            pytdx_amount = float(pytdx_match["amount"])

            # Tushare vol单位: 手, amount单位: 千元
            # pytdx vol单位: 手, amount单位: 元
            # 统一换算后再对比
            pytdx_amount_k = pytdx_amount / 1000.0  # 元 -> 千元

            close_diff = abs(ts_close - pytdx_close)
            close_pct = close_diff / ts_close * 100 if ts_close > 0 else 0
            vol_diff_pct = abs(ts_vol - pytdx_vol) / ts_vol * 100 if ts_vol > 0 else 0
            amount_diff_pct = abs(ts_amount - pytdx_amount_k) / ts_amount * 100 if ts_amount > 0 else 0

            close_ok = close_pct < 0.5
            vol_ok = vol_diff_pct < 1.0
            amount_ok = amount_diff_pct < 1.0

            if not (close_ok and vol_ok and amount_ok):
                all_pass = False

            status = "✅" if (close_ok and vol_ok and amount_ok) else "❌"
            print(f"  {td_str} {status}")
            print(f"    收盘价: Tushare={ts_close:.2f} pytdx={pytdx_close:.2f} 偏差={close_pct:.3f}% {'✅' if close_ok else '❌'}")
            print(f"    成交量: Tushare={ts_vol:.0f}手 pytdx={pytdx_vol:.0f}手 偏差={vol_diff_pct:.3f}% {'✅' if vol_ok else '❌'}")
            print(f"    成交额: Tushare={ts_amount:.0f}千元 pytdx={pytdx_amount_k:.0f}千元 偏差={amount_diff_pct:.3f}% {'✅' if amount_ok else '❌'}")

            # 对比open/high/low
            ts_open = float(ts_row["open"])
            ts_high = float(ts_row["high"])
            ts_low = float(ts_row["low"])
            pytdx_open = float(pytdx_match["open"])
            pytdx_high = float(pytdx_match["high"])
            pytdx_low = float(pytdx_match["low"])
            open_pct = abs(ts_open - pytdx_open) / ts_open * 100 if ts_open > 0 else 0
            high_pct = abs(ts_high - pytdx_high) / ts_high * 100 if ts_high > 0 else 0
            low_pct = abs(ts_low - pytdx_low) / ts_low * 100 if ts_low > 0 else 0
            print(f"    开盘价: Tushare={ts_open:.2f} pytdx={pytdx_open:.2f} 偏差={open_pct:.3f}%")
            print(f"    最高价: Tushare={ts_high:.2f} pytdx={pytdx_high:.2f} 偏差={high_pct:.3f}%")
            print(f"    最低价: Tushare={ts_low:.2f} pytdx={pytdx_low:.2f} 偏差={low_pct:.3f}%")

    api.disconnect()

    print(f"\n{'='*60}")
    if all_pass:
        print("✅ 全部通过: pytdx历史K线与Tushare数据一致(偏差<1%)")
    else:
        print("❌ 存在偏差: 请检查上方标记为❌的项")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
