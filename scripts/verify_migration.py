import sys
sys.path.insert(0, "D:/Python/agent_a_sk")
from src.data.db import Database
from src.data.schema import init_schema

db = Database()
init_schema(db)

cols = db.fetch_df("SELECT column_name FROM information_schema.columns WHERE table_name = 'stock_basic'")
print("stock_basic columns:")
for c in cols["column_name"].tolist():
    print(f"  - {c}")

count = db.fetch_df("SELECT COUNT(*) as cnt FROM stock_basic")
print(f"\nstock_basic rows: {count['cnt'].iloc[0]}")
