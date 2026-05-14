import duckdb
con = duckdb.connect("D:/Python/agent_a_sk/data/stock_agent.duckdb", read_only=True)

# 看有股本数据的60只是什么范围
has_share = con.execute("SELECT ts_code FROM stock_basic WHERE total_share IS NOT NULL AND total_share > 0 ORDER BY ts_code").fetchall()
print(f"有股本数据: {len(has_share)} 只")
for row in has_share[:10]:
    print(f"  {row[0]}")
print("  ...")

# 看无股本数据的
no_share = con.execute("SELECT ts_code FROM stock_basic WHERE total_share IS NULL OR total_share = 0 ORDER BY ts_code LIMIT 10").fetchall()
print(f"\n无股本数据前10只:")
for row in no_share:
    print(f"  {row[0]}")

con.close()
