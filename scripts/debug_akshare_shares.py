import akshare as ak
import pandas as pd

# 测试1: stock_zh_a_spot_em 实时快照（含总市值、流通市值、最新价）
print("=== stock_zh_a_spot_em ===")
df = ak.stock_zh_a_spot_em()
print(f"列名: {df.columns.tolist()}")
print(f"行数: {len(df)}")
# 取一只看看
sample = df.iloc[0]
print(f"\n样本: {sample.to_dict()}")

# 如果有总市值和最新价，可以反算总股本 = 总市值/最新价
print("\n=== 反算股本 ===")
for _, row in df.head(5).iterrows():
    code = str(row.get("代码", "")).zfill(6)
    name = row.get("名称", "")
    close = row.get("最新价", 0)
    total_mv = row.get("总市值", 0)
    circ_mv = row.get("流通市值", 0)
    if close and close > 0 and total_mv and total_mv > 0:
        total_share_wan = total_mv / close  # 万股
        circ_share_wan = circ_mv / close if circ_mv else 0
        print(f"  {code} {name}: close={close}, 总市值={total_mv/1e8:.1f}亿, 总股本={total_share_wan:.0f}万股, 流通股本={circ_share_wan:.0f}万股")
