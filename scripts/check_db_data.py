import duckdb
con = duckdb.connect("D:/Python/agent_a_sk/data/stock_agent.duckdb", read_only=True)

# 检查股本数据
share_cnt = con.execute("SELECT COUNT(*) FROM stock_basic WHERE total_share IS NOT NULL AND total_share > 0").fetchone()
print(f"stock_basic 有股本数据: {share_cnt[0]} 只")

# 检查 daily_basic
db_cnt = con.execute("SELECT COUNT(*) FROM daily_basic").fetchone()
print(f"daily_basic 总行数: {db_cnt[0]}")

db_date = con.execute("SELECT trade_date, COUNT(*) as cnt FROM daily_basic GROUP BY trade_date ORDER BY trade_date DESC LIMIT 5").fetchall()
print(f"daily_basic 最近日期:")
for row in db_date:
    print(f"  {row[0]}: {row[1]} 只")

con.close()
