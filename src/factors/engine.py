import pandas as pd
import numpy as np
from loguru import logger
from typing import Dict, Optional
from ..config import get_config
from ..data.db import Database
from .registry import FactorRegistry
from .valuation import ValuationFactors
from .quality import QualityFactors
from .growth import GrowthFactors
from .momentum import MomentumFactors
from .sentiment import SentimentFactors
from .technical import TechnicalFactors
from .alternative import AlternativeFactors


class FactorEngine:
    _initialized = False

    def __init__(self, db: Optional[Database] = None):
        self.cfg = get_config()
        self.db = db or Database.get_instance(self.cfg.duckdb_path)
        if not FactorEngine._initialized:
            self._register_all_factors()
            FactorEngine._initialized = True

    def _register_all_factors(self):
        ValuationFactors.register_all()
        QualityFactors.register_all()
        GrowthFactors.register_all()
        MomentumFactors.register_all()
        SentimentFactors.register_all()
        TechnicalFactors.register_all()
        AlternativeFactors.register_all()
        count = FactorRegistry.count()
        logger.info(f"已注册 {count} 个因子")

    def compute_all(self, df: pd.DataFrame) -> pd.DataFrame:
        results = {}
        for name, factor in FactorRegistry.all_factors().items():
            try:
                val = factor.calculate(df)
                if isinstance(val, pd.Series):
                    results[name] = val
                else:
                    results[name] = pd.Series(np.nan, index=df.index)
            except Exception as e:
                logger.debug(f"因子 {name} 计算失败: {e}")
                results[name] = pd.Series(np.nan, index=df.index)

        factor_df = pd.DataFrame(results, index=df.index)
        return factor_df

    def neutralize_industry(self, factor_df: pd.DataFrame, industry: pd.Series) -> pd.DataFrame:
        if industry.nunique() <= 1:
            return factor_df
        neutralized = factor_df.copy()
        common_idx = factor_df.index.intersection(industry.index)
        if len(common_idx) == 0:
            return neutralized
        ind_aligned = industry.reindex(common_idx)
        known_mask = ind_aligned != "unknown"
        known_idx = common_idx[known_mask]
        if len(known_idx) == 0:
            return neutralized
        ind_known = ind_aligned[known_mask]
        factor_known = neutralized.loc[known_idx]
        industry_means = factor_known.groupby(ind_known).mean()
        mapped_means = industry_means.loc[ind_known]
        mapped_means.index = known_idx
        neutralized.loc[known_idx] = factor_known.values - mapped_means.values
        return neutralized

    def winsorize(self, factor_df: pd.DataFrame, method: str = "mad", n: float = 3.0) -> pd.DataFrame:
        result = factor_df.copy()
        if method == "mad":
            medians = result.median()
            mads = (result - medians).abs().median() * 1.4826
            lower = medians - n * mads
            upper = medians + n * mads
            result = result.clip(lower=lower, upper=upper, axis=1)
        elif method == "percentile":
            lower = result.quantile(0.01)
            upper = result.quantile(0.99)
            result = result.clip(lower=lower, upper=upper, axis=1)
        return result

    def zscore_normalize(self, factor_df: pd.DataFrame) -> pd.DataFrame:
        means = factor_df.mean()
        stds = factor_df.std()
        stds[stds == 0] = np.nan
        result = (factor_df - means) / stds
        result = result.fillna(0.0)
        return result

    def pipeline(self, df: pd.DataFrame, industry: Optional[pd.Series] = None) -> pd.DataFrame:
        logger.info(f"开始因子计算，输入数据: {len(df)} 行")

        if "ts_code" in df.columns and "trade_date" in df.columns:
            factor_df = self._compute_panel(df)
        else:
            factor_df = self.compute_all(df)

        logger.info(f"因子计算完成: {factor_df.shape[1]} 个因子")

        if industry is not None and self.cfg.factors.neutralization == "industry":
            factor_df = self.neutralize_industry(factor_df, industry)
            logger.info("行业中性化完成")

        factor_df = self.winsorize(factor_df, method=self.cfg.factors.extreme_value_method)
        logger.info("去极值完成")

        factor_df = self.zscore_normalize(factor_df)
        logger.info("Z-Score标准化完成")

        return factor_df

    def _compute_panel(self, df: pd.DataFrame) -> pd.DataFrame:
        all_results = []
        for ts_code, group in df.groupby("ts_code"):
            group = group.sort_values("trade_date")
            group = group.reset_index(drop=True)
            try:
                factor_series = self.compute_all(group)
                factor_series.index = [ts_code] * len(factor_series)
                factor_series["_trade_date"] = group["trade_date"].values
                factor_series["_ts_code"] = ts_code
                all_results.append(factor_series)
            except Exception as e:
                logger.debug(f"股票 {ts_code} 因子计算失败: {e}")
                continue

        if not all_results:
            return pd.DataFrame()

        combined = pd.concat(all_results, axis=0)

        trade_dates = combined.pop("_trade_date")
        combined.pop("_ts_code")

        latest_date = trade_dates.max()
        mask = trade_dates == latest_date
        latest_factors = combined.loc[mask].copy()
        latest_factors.index.name = "ts_code"

        return latest_factors

    def _to_date(self, trade_date: str) -> str:
        if len(trade_date) == 8:
            return f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        return trade_date

    def save_factors(self, factor_df: pd.DataFrame, trade_date: str):
        dt = self._to_date(trade_date)
        factor_df_copy = factor_df.copy()
        factor_df_copy.index.name = "ts_code"
        melted = factor_df_copy.reset_index().melt(
            id_vars="ts_code", var_name="factor_name", value_name="factor_value"
        )
        melted = melted.dropna(subset=["factor_value"])
        melted["trade_date"] = pd.to_datetime(dt)
        melted = melted[["ts_code", "trade_date", "factor_name", "factor_value"]]

        if not melted.empty:
            temp = f"temp_factors_{int(pd.Timestamp.now().timestamp()*1000)}"
            self.db.conn.register(temp, melted)
            self.db.execute(f"DELETE FROM factors_daily WHERE trade_date = '{dt}'")
            self.db.execute(f"INSERT INTO factors_daily SELECT * FROM {temp}")
            self.db.conn.unregister(temp)
            logger.info(f"因子数据已保存: {trade_date}, {len(melted)} 条记录")

    def get_factor_weights(self, trade_date: str) -> Dict[str, float]:
        dt = self._to_date(trade_date)
        sql = """
        SELECT factor_name, weight
        FROM factor_weights_history
        WHERE effective_date <= ?
        AND approved = TRUE
        ORDER BY effective_date DESC, factor_name
        """
        rows = self.db.fetch_all(sql, [dt])
        if not rows:
            n = FactorRegistry.count()
            if n == 0:
                return {}
            w = 1.0 / n
            return {name: w for name in FactorRegistry.factor_names()}
        return {row[0]: row[1] for row in rows}

    def score_stocks(self, factor_df: pd.DataFrame, weights: Dict[str, float]) -> pd.Series:
        common = set(factor_df.columns) & set(weights.keys())
        if not common:
            return pd.Series(0.0, index=factor_df.index)
        score = pd.Series(0.0, index=factor_df.index)
        for name in common:
            score += factor_df[name] * weights[name]
        return score
