import duckdb

db_path = "D:/Python/agent_a_sk/data/stock_agent.duckdb"
con = duckdb.connect(db_path)

cols = con.execute("SELECT column_name FROM information_schema.columns WHERE table_name='stock_basic'").fetchall()
existing = set(c[0] for c in cols)

if "total_share" not in existing:
    con.execute("ALTER TABLE stock_basic ADD COLUMN total_share DOUBLE")
    print("Added total_share column")
else:
    print("total_share already exists")

if "circ_share" not in existing:
    con.execute("ALTER TABLE stock_basic ADD COLUMN circ_share DOUBLE")
    print("Added circ_share column")
else:
    print("circ_share already exists")

cols2 = con.execute("SELECT column_name FROM information_schema.columns WHERE table_name='stock_basic'").fetchall()
print("\nstock_basic columns after migration:")
for c in cols2:
    print(f"  - {c[0]}")

con.close()
print("\nMigration complete!")
