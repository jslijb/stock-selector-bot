import duckdb
con = duckdb.connect("D:/Python/agent_a_sk/data/stock_agent.duckdb", read_only=True)

# 看stock_basic里ts_code的格式
sample = con.execute("SELECT ts_code, total_share, circ_share FROM stock_basic WHERE total_share IS NOT NULL LIMIT 5").fetchall()
print("有股本数据的 ts_code 样本:")
for row in sample:
    print(f"  {row}")

# 看stock_basic里总体的ts_code格式
sample2 = con.execute("SELECT ts_code, symbol, name FROM stock_basic LIMIT 5").fetchall()
print("\nstock_basic 前5行:")
for row in sample2:
    print(f"  ts_code={row[0]}, symbol={row[1]}, name={row[2]}")

# 东方财富的code格式: 600000 -> 600000.SH
# 看一下有多少是SH/SZ结尾的
sh_cnt = con.execute("SELECT COUNT(*) FROM stock_basic WHERE ts_code LIKE '%.SH'").fetchone()
sz_cnt = con.execute("SELECT COUNT(*) FROM stock_basic WHERE ts_code LIKE '%.SZ'").fetchone()
bj_cnt = con.execute("SELECT COUNT(*) FROM stock_basic WHERE ts_code LIKE '%.BJ'").fetchone()
other_cnt = con.execute("SELECT COUNT(*) FROM stock_basic WHERE ts_code NOT LIKE '%.__'").fetchone()
print(f"\nts_code后缀分布: SH={sh_cnt[0]}, SZ={sz_cnt[0]}, BJ={bj_cnt[0]}, other={other_cnt[0]}")

con.close()
