import duckdb
import sys

db_path = "D:/Python/agent_a_sk/data/stock_agent.duckdb"
try:
    conn = duckdb.connect(db_path, read_only=True)
except Exception as e:
    print(f"无法打开数据库: {e}")
    sys.exit(1)

print("=== 1. money_flow 各日期数据量 ===")
for dt in ["2026-02-04", "2026-05-20", "2024-03-01"]:
    try:
        cnt = conn.execute(f"SELECT COUNT(*) FROM money_flow WHERE trade_date = '{dt}'").fetchone()
        print(f"  {dt}: {cnt[0]} 条")
    except Exception as e:
        print(f"  {dt}: 查询失败 {e}")

print("\n=== 2. daily_basic 各日期数据量 ===")
for dt in ["2026-02-04", "2026-05-20", "2024-03-01"]:
    try:
        cnt = conn.execute(f"SELECT COUNT(*) FROM daily_basic WHERE trade_date = '{dt}'").fetchone()
        print(f"  {dt}: {cnt[0]} 条")
    except Exception as e:
        print(f"  {dt}: 查询失败 {e}")

print("\n=== 3. money_flow中有但daily_basic中无市值数据的股票(2026-02-04) ===")
try:
    no_mv = conn.execute("""
        SELECT COUNT(*)
        FROM money_flow mf
        LEFT JOIN daily_basic db ON mf.ts_code = db.ts_code AND db.trade_date = '2026-02-04'
        WHERE mf.trade_date = '2026-02-04' AND db.total_mv IS NULL
    """).fetchone()
    print(f"  无市值数据: {no_mv[0]} 只")

    no_mv_list = conn.execute("""
        SELECT mf.ts_code
        FROM money_flow mf
        LEFT JOIN daily_basic db ON mf.ts_code = db.ts_code AND db.trade_date = '2026-02-04'
        WHERE mf.trade_date = '2026-02-04' AND db.total_mv IS NULL
        LIMIT 10
    """).fetchall()
    for r in no_mv_list:
        print(f"    {r[0]}")
except Exception as e:
    print(f"  查询失败: {e}")

print("\n=== 4. money_flow中市值 < 100亿的股票(2026-02-04) ===")
try:
    small_cap = conn.execute("""
        SELECT mf.ts_code, ROUND(db.total_mv / 10000.0, 2) as cap_yi
        FROM money_flow mf
        JOIN daily_basic db ON mf.ts_code = db.ts_code AND db.trade_date = '2026-02-04'
        WHERE mf.trade_date = '2026-02-04' AND db.total_mv < 1000000.0
        ORDER BY db.total_mv ASC
    """).fetchall()
    print(f"  市值 < 100亿: {len(small_cap)} 只")
    for r in small_cap[:20]:
        print(f"    {r[0]}: {r[1]} 亿")
except Exception as e:
    print(f"  查询失败: {e}")

print("\n=== 5. 对比 2024-03-01 市值 < 100亿情况 ===")
try:
    small_2024 = conn.execute("""
        SELECT COUNT(*)
        FROM money_flow mf
        JOIN daily_basic db ON mf.ts_code = db.ts_code AND db.trade_date = '2024-03-01'
        WHERE mf.trade_date = '2024-03-01' AND db.total_mv < 1000000.0
    """).fetchone()
    print(f"  市值 < 100亿: {small_2024[0]} 只")
except Exception as e:
    print(f"  查询失败: {e}")

print("\n=== 6. decisions 中持仓的小市值股票(2026-02-04) ===")
try:
    dec_small = conn.execute("""
        SELECT d.ts_code, d.weight, ROUND(db.total_mv / 10000.0, 2) as cap_yi
        FROM decisions d
        JOIN daily_basic db ON d.ts_code = db.ts_code AND db.trade_date = '2026-02-04'
        WHERE d.trade_date = '2026-02-04' AND db.total_mv < 1000000.0
        ORDER BY db.total_mv ASC
    """).fetchall()
    print(f"  decisions中市值 < 100亿持仓: {len(dec_small)} 只")
    for r in dec_small[:10]:
        print(f"    {r[0]}: weight={r[1]}, cap={r[2]} 亿")
except Exception as e:
    print(f"  查询失败: {e}")

print("\n=== 7. _pre_screen 应过滤的：在factors_daily中但在decisions中且市值<100亿 ===")
try:
    leaked = conn.execute("""
        SELECT f.ts_code, ROUND(db.total_mv / 10000.0, 2) as cap_yi
        FROM (
            SELECT DISTINCT ts_code FROM factors_daily WHERE trade_date = '2026-02-04'
        ) f
        JOIN decisions d ON f.ts_code = d.ts_code AND d.trade_date = '2026-02-04'
        JOIN daily_basic db ON f.ts_code = db.ts_code AND db.trade_date = '2026-02-04'
        WHERE db.total_mv < 1000000.0
        ORDER BY db.total_mv ASC
    """).fetchall()
    print(f"  通过初筛但市值<100亿的持仓: {len(leaked)} 只")
    for r in leaked[:10]:
        print(f"    {r[0]}: {r[1]} 亿")
except Exception as e:
    print(f"  查询失败: {e}")

conn.close()
