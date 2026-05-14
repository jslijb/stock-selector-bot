import duckdb
con = duckdb.connect("D:/Python/agent_a_sk/data/stock_agent.duckdb", read_only=True)
cols = con.execute("SELECT column_name FROM information_schema.columns WHERE table_name='stock_basic'").fetchall()
print("stock_basic columns:")
for c in cols:
    print(f"  - {c[0]}")
cnt = con.execute("SELECT COUNT(*) FROM stock_basic").fetchone()
print(f"\nTotal rows: {cnt[0]}")
con.close()
