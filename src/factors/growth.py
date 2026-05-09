import pandas as pd
import numpy as np
from .base import FactorBase
from .registry import FactorRegistry


class GrowthFactors:
    @staticmethod
    def register_all():
        FactorRegistry.register(_RevenueYoY())
        FactorRegistry.register(_ProfitYoY())
        FactorRegistry.register(_OpProfitYoY())
        FactorRegistry.register(_RevenueQoQ())
        FactorRegistry.register(_ProfitQoQ())
        FactorRegistry.register(_EPSGrowth())
        FactorRegistry.register(_BPSGrowth())
        FactorRegistry.register(_AssetGrowth())
        FactorRegistry.register(_EquityGrowth())
        FactorRegistry.register(_OCFGrowth())
        FactorRegistry.register(_RevenueAccel())
        FactorRegistry.register(_ProfitAccel())
        FactorRegistry.register(_SustainableGrowth())
        FactorRegistry.register(_EarningsSurprise())
        FactorRegistry.register(_RevenueStability())


class _RevenueYoY(FactorBase):
    name = "revenue_yoy"
    category = "growth"
    description = "营收同比增长"
    def calculate(self, df, **kw): return df.get("or_yoys", pd.Series(np.nan, index=df.index))

class _ProfitYoY(FactorBase):
    name = "profit_yoy"
    category = "growth"
    description = "净利润同比增长"
    def calculate(self, df, **kw): return df.get("np_yoys", pd.Series(np.nan, index=df.index))

class _OpProfitYoY(FactorBase):
    name = "op_profit_yoy"
    category = "growth"
    description = "营业利润同比增长"
    def calculate(self, df, **kw): return df.get("op_yoys", pd.Series(np.nan, index=df.index))

class _RevenueQoQ(FactorBase):
    name = "revenue_qoq"
    category = "growth"
    description = "营收环比增长"
    def calculate(self, df, **kw): return df.get("or_qoq", pd.Series(np.nan, index=df.index))

class _ProfitQoQ(FactorBase):
    name = "profit_qoq"
    category = "growth"
    description = "净利润环比增长"
    def calculate(self, df, **kw): return df.get("np_qoq", pd.Series(np.nan, index=df.index))

class _EPSGrowth(FactorBase):
    name = "eps_growth"
    category = "growth"
    description = "EPS增长率"
    def calculate(self, df, **kw): return df.get("eps_yoy", pd.Series(np.nan, index=df.index))

class _BPSGrowth(FactorBase):
    name = "bps_growth"
    category = "growth"
    description = "BPS增长率"
    def calculate(self, df, **kw): return df.get("bps_yoy", pd.Series(np.nan, index=df.index))

class _AssetGrowth(FactorBase):
    name = "asset_growth"
    category = "growth"
    description = "总资产增长率"
    def calculate(self, df, **kw): return df.get("total_assets_yoy", pd.Series(np.nan, index=df.index))

class _EquityGrowth(FactorBase):
    name = "equity_growth"
    category = "growth"
    description = "净资产增长率"
    def calculate(self, df, **kw): return df.get("equity_yoy", pd.Series(np.nan, index=df.index))

class _OCFGrowth(FactorBase):
    name = "ocf_growth"
    category = "growth"
    description = "经营现金流增长率"
    def calculate(self, df, **kw): return df.get("ocf_yoy", pd.Series(np.nan, index=df.index))

class _RevenueAccel(FactorBase):
    name = "revenue_accel"
    category = "growth"
    description = "营收增长加速度"
    def calculate(self, df, **kw):
        yoy = df.get("or_yoys", pd.Series(np.nan, index=df.index))
        return yoy.diff()

class _ProfitAccel(FactorBase):
    name = "profit_accel"
    category = "growth"
    description = "利润增长加速度"
    def calculate(self, df, **kw):
        yoy = df.get("np_yoys", pd.Series(np.nan, index=df.index))
        return yoy.diff()

class _SustainableGrowth(FactorBase):
    name = "sustainable_growth"
    category = "growth"
    description = "可持续增长率"
    def calculate(self, df, **kw):
        roe = df.get("roe", pd.Series(np.nan, index=df.index))
        rr = df.get("retention_ratio", pd.Series(0.6, index=df.index))
        return roe * rr

class _EarningsSurprise(FactorBase):
    name = "earnings_surprise"
    category = "growth"
    description = "盈利惊喜"
    def calculate(self, df, **kw): return df.get("earnings_surprise", pd.Series(np.nan, index=df.index))

class _RevenueStability(FactorBase):
    name = "revenue_stability"
    category = "growth"
    description = "营收增长稳定性"
    def calculate(self, df, **kw):
        yoy = df.get("or_yoys", pd.Series(np.nan, index=df.index))
        return -yoy.rolling(8, min_periods=3).std()
