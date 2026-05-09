import numpy as np
import pandas as pd
from loguru import logger
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from scipy.optimize import minimize
from ..config import get_config
from ..data.db import Database
from ..factors.registry import FactorRegistry


def _to_date(d: str) -> str:
    if len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d


class FactorEvolver:
    def __init__(self, db: Optional[Database] = None):
        self.cfg = get_config()
        self.db = db or Database.get_instance(self.cfg.duckdb_path)
        self.lb, self.ub = self.cfg.evolution.weight_bounds

    def compute_rank_ic(self, factor_values: pd.Series, forward_returns: pd.Series) -> float:
        common = factor_values.index.intersection(forward_returns.index)
        if len(common) < 10:
            return np.nan
        f = factor_values.loc[common].rank()
        r = forward_returns.loc[common].rank()
        ic = f.corr(r, method="spearman")
        return ic

    def compute_ic_matrix(self, factor_df: pd.DataFrame, return_series: pd.Series,
                          window: int = 60) -> Tuple[pd.Series, pd.DataFrame]:
        factor_names = factor_df.columns.tolist()
        ic_values = {}
        for name in factor_names:
            f = factor_df[name]
            if f.std() == 0 or f.isna().all():
                ic_values[name] = 0.0
                continue
            ic = self.compute_rank_ic(f, return_series)
            ic_values[name] = ic if not pd.isna(ic) else 0.0
        ic_mean = pd.Series(ic_values)
        ic_cov = pd.DataFrame(0.0, index=factor_names, columns=factor_names)
        np.fill_diagonal(ic_cov.values, 0.01)
        return ic_mean, ic_cov

    def optimize_weights(self, ic_mean: pd.Series, ic_cov: pd.DataFrame) -> Dict[str, float]:
        n = len(ic_mean)
        if n == 0:
            return {}

        factor_names = ic_mean.index.tolist()
        mu = ic_mean.values
        cov = ic_cov.values

        def neg_ir(w):
            w = np.array(w)
            port_ic = w @ mu
            port_var = w @ cov @ w
            if port_var <= 0:
                return 1e10
            return -port_ic / np.sqrt(port_var)

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        bounds = [(self.lb, self.ub)] * n
        x0 = np.ones(n) / n

        result = minimize(neg_ir, x0, method="SLSQP", bounds=bounds, constraints=constraints,
                          options={"maxiter": 200, "ftol": 1e-6})

        if result.success:
            weights = {factor_names[i]: result.x[i] for i in range(n)}
            logger.info(f"权重优化成功, IR = {-result.fun:.4f}")
            return weights
        else:
            logger.warning(f"权重优化失败: {result.message}")
            return {name: 1.0 / n for name in factor_names}

    def run_monthly_evolution(self, current_date: str) -> Dict:
        logger.info(f"=== 月度进化: {current_date} ===")

        months = self.cfg.evolution.ic_window_months
        end_dt = datetime.strptime(current_date, "%Y%m%d")
        start_dt = end_dt - timedelta(days=months * 30)
        start_str = start_dt.strftime("%Y%m%d")

        factor_names = FactorRegistry.factor_names()
        if not factor_names:
            logger.warning("无注册因子，跳过进化")
            return {}

        sql = """
        SELECT f.ts_code, f.trade_date, f.factor_name, f.factor_value,
               d.close as current_close,
               LEAD(d.close) OVER (PARTITION BY f.ts_code ORDER BY d.trade_date) as next_close
        FROM factors_daily f
        JOIN daily_price d ON f.ts_code = d.ts_code AND f.trade_date = d.trade_date
        WHERE f.trade_date BETWEEN ? AND ?
        """
        try:
            raw = self.db.fetch_df(sql, [_to_date(start_str), _to_date(current_date)])
        except Exception as e:
            logger.error(f"获取因子数据失败: {e}")
            return {}

        if raw.empty:
            logger.warning("无数据可进化")
            return {}

        raw["forward_return"] = raw["next_close"] / raw["current_close"] - 1
        pivot = raw.pivot_table(index=["ts_code", "trade_date"], columns="factor_name", values="factor_value")
        returns = raw.drop_duplicates(subset=["ts_code", "trade_date"]).set_index(["ts_code", "trade_date"])["forward_return"]

        ic_mean, ic_cov = self.compute_ic_matrix(pivot, returns)
        new_weights = self.optimize_weights(ic_mean, ic_cov)

        effective_dt = _to_date(current_date)
        for name, w in new_weights.items():
            ic_m = ic_mean.get(name, 0)
            ic_s = np.sqrt(ic_cov.loc[name, name]) if name in ic_cov.index else 0
            ir = ic_m / ic_s if ic_s > 0 else 0
            self.db.execute(
                """INSERT INTO factor_weights_history
                (effective_date, factor_name, weight, ic_mean, ic_std, ir, approved)
                VALUES (?, ?, ?, ?, ?, ?, FALSE)""",
                [effective_dt, name, w, ic_m, ic_s, ir],
            )

        logger.info(f"新权重已写入(待审核): {len(new_weights)} 个因子")
        return new_weights

    def approve_weights(self, effective_date: str):
        self.db.execute(
            "UPDATE factor_weights_history SET approved = TRUE WHERE effective_date = ? AND approved = FALSE",
            [effective_date],
        )
        logger.info(f"权重已批准生效: {effective_date}")

    def get_pending_weights(self) -> pd.DataFrame:
        return self.db.fetch_df(
            "SELECT effective_date, factor_name, weight, ic_mean, ic_std, ir FROM factor_weights_history WHERE approved = FALSE ORDER BY effective_date DESC, factor_name"
        )

    def evaluate_performance(self, trade_date: str, lookback_days: int = 20):
        dt = _to_date(trade_date)
        decisions = self.db.fetch_df(
            "SELECT trade_date, ts_code, weight FROM decisions WHERE trade_date <= ? ORDER BY trade_date DESC",
            [dt],
        )
        if decisions.empty:
            return

        dates = decisions["trade_date"].unique()[:lookback_days]
        for d in dates:
            day_holdings = decisions[decisions["trade_date"] == d]
            for _, row in day_holdings.iterrows():
                ts_code = row["ts_code"]
                weight = row["weight"]
                price_sql = """
                SELECT trade_date, close FROM daily_price
                WHERE ts_code = ? AND trade_date >= ?
                ORDER BY trade_date LIMIT 21
                """
                prices = self.db.fetch_df(price_sql, [ts_code, d])
                if len(prices) < 2:
                    continue
                base = prices.iloc[0]["close"]
                for n_day, label in [(1, "return_1d"), (3, "return_3d"), (5, "return_5d"), (10, "return_10d"), (20, "return_20d")]:
                    if n_day < len(prices):
                        ret = prices.iloc[n_day]["close"] / base - 1
                    else:
                        ret = np.nan
                    self.db.execute(
                        f"""INSERT OR IGNORE INTO decision_performance
                        (trade_date, ts_code, decision_weight, {label})
                        VALUES (?, ?, ?, ?)""",
                        [d, ts_code, weight, ret],
                    )
        logger.info(f"绩效评估完成: {trade_date}")

    def evaluate_performance_bulk(self, trade_dates: list, lookback_days: int = 20):
        if not trade_dates:
            return
        logger.info(f"批量绩效评估: {len(trade_dates)} 天")
        decisions = self.db.fetch_df(
            "SELECT trade_date, ts_code, weight FROM decisions ORDER BY trade_date DESC"
        )
        if decisions.empty:
            return

        all_dates = decisions["trade_date"].unique()
        recent_dates = all_dates[:lookback_days * 2]

        records = []
        trade_dates_set = set(trade_dates)
        for d in recent_dates:
            d_str = d.strftime("%Y%m%d") if hasattr(d, "strftime") else str(d)[:10].replace("-", "")
            if d_str not in trade_dates_set:
                continue
            day_holdings = decisions[decisions["trade_date"] == d]
            if day_holdings.empty:
                continue
            for _, row in day_holdings.iterrows():
                ts_code = row["ts_code"]
                weight = row["weight"]
                price_sql = """
                SELECT trade_date, close FROM daily_price
                WHERE ts_code = ? AND trade_date >= ?
                ORDER BY trade_date LIMIT 21
                """
                prices = self.db.fetch_df(price_sql, [ts_code, d])
                if len(prices) < 2:
                    continue
                base = prices.iloc[0]["close"]
                ret_1d = prices.iloc[1]["close"] / base - 1 if len(prices) >= 2 else np.nan
                ret_3d = prices.iloc[3]["close"] / base - 1 if len(prices) >= 4 else np.nan
                ret_5d = prices.iloc[5]["close"] / base - 1 if len(prices) >= 6 else np.nan
                ret_10d = prices.iloc[10]["close"] / base - 1 if len(prices) >= 11 else np.nan
                ret_20d = prices.iloc[20]["close"] / base - 1 if len(prices) >= 21 else np.nan
                records.append({
                    "trade_date": d,
                    "ts_code": ts_code,
                    "decision_weight": weight,
                    "return_1d": ret_1d,
                    "return_3d": ret_3d,
                    "return_5d": ret_5d,
                    "return_10d": ret_10d,
                    "return_20d": ret_20d,
                })

        if records:
            df = pd.DataFrame(records)
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            insert_cols = "trade_date, ts_code, decision_weight, return_1d, return_3d, return_5d, return_10d, return_20d"
            temp = f"temp_perf_{int(pd.Timestamp.now().timestamp()*1000)}"
            self.db.conn.register(temp, df)
            self.db.execute(f"INSERT OR IGNORE INTO decision_performance ({insert_cols}) SELECT {insert_cols} FROM {temp}")
            try:
                self.db.conn.unregister(temp)
            except Exception:
                pass
            logger.info(f"批量绩效评估完成: {len(records)} 条")
