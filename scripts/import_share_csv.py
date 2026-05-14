import sys
sys.path.insert(0, "D:/Python/agent_a_sk")

import pandas as pd
import duckdb
from loguru import logger

DB_PATH = "D:/Python/agent_a_sk/data/stock_agent.duckdb"
CSV_PATH = "D:/Python/agent_a_sk/data/share_cache.csv"


def _code_to_ts(code):
    code = str(code).zfill(6)
    if code.startswith("6"):
        return f"{code}.SH"
    elif code.startswith("0") or code.startswith("3"):
        return f"{code}.SZ"
    elif code.startswith("8") or code.startswith("4"):
        return f"{code}.BJ"
    return f"{code}.SZ"


def main():
    df = pd.read_csv(CSV_PATH, encoding="utf-8-sig")
    print(f"CSV行数: {len(df)}")
    print(f"CSV列: {df.columns.tolist()}")

    records = []
    for _, row in df.iterrows():
        code = str(row.get("证券代码", "")).zfill(6)
        total_share = row.get("总股本")
        circ_share = row.get("已流通股份")

        if not code or not total_share or pd.isna(total_share) or float(total_share) <= 0:
            continue

        ts_code = _code_to_ts(code)
        records.append({
            "ts_code": ts_code,
            "total_share": float(total_share),
            "circ_share": float(circ_share) if not pd.isna(circ_share) else None,
        })

    print(f"有效记录: {len(records)}")

    if not records:
        print("无有效数据，退出")
        return

    share_df = pd.DataFrame(records)
    print(f"样本:")
    for _, r in share_df.head(5).iterrows():
        cs = f"{r['circ_share']:.2f}" if r['circ_share'] else "None"
        print(f"  {r['ts_code']}: total_share={r['total_share']:.2f}, circ_share={cs}")

    con = duckdb.connect(DB_PATH)

    before = con.execute("SELECT COUNT(*) FROM stock_basic WHERE total_share IS NOT NULL AND total_share > 0").fetchone()[0]
    print(f"\n导入前: {before} 只有股本数据")

    temp = "temp_share_import"
    con.register(temp, share_df)
    con.execute(
        f"UPDATE stock_basic SET total_share = s.total_share, circ_share = s.circ_share "
        f"FROM {temp} s WHERE stock_basic.ts_code = s.ts_code"
    )
    try:
        con.unregister(temp)
    except Exception:
        pass

    after = con.execute("SELECT COUNT(*) FROM stock_basic WHERE total_share IS NOT NULL AND total_share > 0").fetchone()[0]
    print(f"导入后: {after} 只有股本数据")
    print(f"本次更新: {after - before} 只")

    con.close()
    print("\n导入完成!")


if __name__ == "__main__":
    main()
