import duckdb
con = duckdb.connect("D:/Python/agent_a_sk/data/stock_agent.duckdb", read_only=True)

# daily_price 覆盖范围
dp_range = con.execute("SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date) FROM daily_price").fetchone()
print(f"daily_price: {dp_range[0]} ~ {dp_range[1]}, {dp_range[2]}个交易日")

# daily_basic 覆盖范围
db_range = con.execute("SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date) FROM daily_basic").fetchone()
print(f"daily_basic: {db_range[0]} ~ {db_range[1]}, {db_range[2]}个交易日")

# factors_daily 覆盖范围
try:
    f_range = con.execute("SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date) FROM factors_daily").fetchone()
    print(f"factors_daily: {f_range[0]} ~ {f_range[1]}, {f_range[2]}个交易日")
except:
    print("factors_daily: 无数据")

# decisions 覆盖范围
try:
    d_range = con.execute("SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date) FROM decisions").fetchone()
    print(f"decisions: {d_range[0]} ~ {d_range[1]}, {d_range[2]}个交易日")
except:
    print("decisions: 无数据")

# moneyflow 覆盖范围
try:
    m_range = con.execute("SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date) FROM moneyflow").fetchone()
    print(f"moneyflow: {m_range[0]} ~ {m_range[1]}, {m_range[2]}个交易日")
except:
    print("moneyflow: 无数据")

# financials 覆盖范围
try:
    fin_cnt = con.execute("SELECT COUNT(*) FROM financials").fetchone()[0]
    print(f"financials: {fin_cnt} 行")
except:
    print("financials: 无数据")

# 缺失分析：daily_price有但daily_basic没有的交易日
missing = con.execute("""
    SELECT COUNT(DISTINCT dp.trade_date)
    FROM daily_price dp
    LEFT JOIN daily_basic db ON dp.trade_date = db.trade_date
    WHERE db.trade_date IS NULL
""").fetchone()[0]
print(f"\ndaily_price有但daily_basic缺失: {missing}个交易日")

con.close()
