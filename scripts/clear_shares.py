import duckdb
con = duckdb.connect("D:/Python/agent_a_sk/data/stock_agent.duckdb")
cnt = con.execute("SELECT COUNT(*) FROM stock_basic WHERE total_share IS NOT NULL AND total_share > 0").fetchone()
print(f"清空前: {cnt[0]} 只有股本数据")
con.execute("UPDATE stock_basic SET total_share = NULL, circ_share = NULL WHERE total_share IS NOT NULL")
cnt2 = con.execute("SELECT COUNT(*) FROM stock_basic WHERE total_share IS NOT NULL AND total_share > 0").fetchone()
print(f"清空后: {cnt2[0]} 只有股本数据")
con.close()
