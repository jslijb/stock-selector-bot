import pandas as pd
import numpy as np
from .base import FactorBase
from .registry import FactorRegistry


class QualityFactors:
    @staticmethod
    def register_all():
        FactorRegistry.register(_ROE())
        FactorRegistry.register(_ROA())
        FactorRegistry.register(_ROIC())
        FactorRegistry.register(_GrossMargin())
        FactorRegistry.register(_NetMargin())
        FactorRegistry.register(_OperatingMargin())
        FactorRegistry.register(_AssetTurnover())
        FactorRegistry.register(_InventoryTurnover())
        FactorRegistry.register(_DebtToEquity())
        FactorRegistry.register(_CurrentRatio())
        FactorRegistry.register(_QuickRatio())
        FactorRegistry.register(_InterestCoverage())
        FactorRegistry.register(_Accruals())
        FactorRegistry.register(_Sloan())
        FactorRegistry.register(_ROEStability())
        FactorRegistry.register(_EarningsQuality())
        FactorRegistry.register(_LeverageRatio())
        FactorRegistry.register(_EquityRatio())
        FactorRegistry.register(_CashRatio())
        FactorRegistry.register(_OperatingEfficiency())


class _ROE(FactorBase):
    name = "roe"
    category = "quality"
    description = "净资产收益率"
    def calculate(self, df, **kw): return df.get("roe", pd.Series(np.nan, index=df.index))

class _ROA(FactorBase):
    name = "roa"
    category = "quality"
    description = "总资产收益率"
    def calculate(self, df, **kw):
        np_val = df.get("net_profit", pd.Series(np.nan, index=df.index))
        ta = df.get("total_assets", pd.Series(np.nan, index=df.index))
        return np_val / ta.replace(0, np.nan)

class _ROIC(FactorBase):
    name = "roic"
    category = "quality"
    description = "投入资本回报率"
    def calculate(self, df, **kw):
        op = df.get("total_revenue", pd.Series(np.nan, index=df.index)) - df.get("total_cogs", pd.Series(np.nan, index=df.index))
        ic = df.get("total_hldr_eqy", pd.Series(np.nan, index=df.index)) + df.get("total_liab", pd.Series(0, index=df.index))
        return op / ic.replace(0, np.nan)

class _GrossMargin(FactorBase):
    name = "gross_margin"
    category = "quality"
    description = "毛利率"
    def calculate(self, df, **kw):
        rev = df.get("revenue", pd.Series(np.nan, index=df.index))
        cost = df.get("oper_cost", pd.Series(np.nan, index=df.index))
        return (rev - cost) / rev.replace(0, np.nan)

class _NetMargin(FactorBase):
    name = "net_margin"
    category = "quality"
    description = "净利率"
    def calculate(self, df, **kw):
        np_val = df.get("net_profit", pd.Series(np.nan, index=df.index))
        rev = df.get("total_revenue", pd.Series(np.nan, index=df.index))
        return np_val / rev.replace(0, np.nan)

class _OperatingMargin(FactorBase):
    name = "operating_margin"
    category = "quality"
    description = "营业利润率"
    def calculate(self, df, **kw):
        rev = df.get("total_revenue", pd.Series(np.nan, index=df.index))
        op_cost = df.get("oper_cost", pd.Series(np.nan, index=df.index))
        sell = df.get("sell_exp", pd.Series(0, index=df.index))
        admin = df.get("admin_exp", pd.Series(0, index=df.index))
        return (rev - op_cost - sell - admin) / rev.replace(0, np.nan)

class _AssetTurnover(FactorBase):
    name = "asset_turnover"
    category = "quality"
    description = "资产周转率"
    def calculate(self, df, **kw):
        rev = df.get("total_revenue", pd.Series(np.nan, index=df.index))
        ta = df.get("total_assets", pd.Series(np.nan, index=df.index))
        return rev / ta.replace(0, np.nan)

class _InventoryTurnover(FactorBase):
    name = "inventory_turnover"
    category = "quality"
    description = "存货周转率"
    def calculate(self, df, **kw):
        cost = df.get("oper_cost", pd.Series(np.nan, index=df.index))
        inv = df.get("inventory", pd.Series(np.nan, index=df.index))
        return cost / inv.replace(0, np.nan)

class _DebtToEquity(FactorBase):
    name = "debt_to_equity"
    category = "quality"
    description = "资产负债率"
    def calculate(self, df, **kw):
        tl = df.get("total_liab", pd.Series(np.nan, index=df.index))
        eq = df.get("total_hldr_eqy", pd.Series(np.nan, index=df.index))
        return tl / eq.replace(0, np.nan)

class _CurrentRatio(FactorBase):
    name = "current_ratio"
    category = "quality"
    description = "流动比率"
    def calculate(self, df, **kw): return df.get("current_ratio", pd.Series(np.nan, index=df.index))

class _QuickRatio(FactorBase):
    name = "quick_ratio"
    category = "quality"
    description = "速动比率"
    def calculate(self, df, **kw): return df.get("quick_ratio", pd.Series(np.nan, index=df.index))

class _InterestCoverage(FactorBase):
    name = "interest_coverage"
    category = "quality"
    description = "利息覆盖倍数"
    def calculate(self, df, **kw): return df.get("interest_coverage", pd.Series(np.nan, index=df.index))

class _Accruals(FactorBase):
    name = "accruals"
    category = "quality"
    description = "应计利润占比"
    def calculate(self, df, **kw):
        np_val = df.get("net_profit", pd.Series(np.nan, index=df.index))
        ocf = df.get("ocf_ps", pd.Series(np.nan, index=df.index)) * df.get("total_hldr_eqy", pd.Series(1, index=df.index))
        return (np_val - ocf) / df.get("total_assets", pd.Series(np.nan, index=df.index)).replace(0, np.nan)

class _Sloan(FactorBase):
    name = "sloan"
    category = "quality"
    description = "Sloan应计项"
    def calculate(self, df, **kw): return df.get("accruals", pd.Series(np.nan, index=df.index))

class _ROEStability(FactorBase):
    name = "roe_stability"
    category = "quality"
    description = "ROE稳定性(负标准差)"
    def calculate(self, df, **kw):
        roe = df.get("roe", pd.Series(np.nan, index=df.index))
        return -roe.rolling(8, min_periods=3).std()

class _EarningsQuality(FactorBase):
    name = "earnings_quality"
    category = "quality"
    description = "盈利质量(经营现金流/净利润)"
    def calculate(self, df, **kw):
        ocf = df.get("ocf_ps", pd.Series(np.nan, index=df.index))
        eps = df.get("eps", pd.Series(np.nan, index=df.index))
        return ocf / eps.replace(0, np.nan)

class _LeverageRatio(FactorBase):
    name = "leverage_ratio"
    category = "quality"
    description = "杠杆率"
    def calculate(self, df, **kw):
        tl = df.get("total_liab", pd.Series(np.nan, index=df.index))
        ta = df.get("total_assets", pd.Series(np.nan, index=df.index))
        return tl / ta.replace(0, np.nan)

class _EquityRatio(FactorBase):
    name = "equity_ratio"
    category = "quality"
    description = "权益比"
    def calculate(self, df, **kw):
        eq = df.get("total_hldr_eqy", pd.Series(np.nan, index=df.index))
        ta = df.get("total_assets", pd.Series(np.nan, index=df.index))
        return eq / ta.replace(0, np.nan)

class _CashRatio(FactorBase):
    name = "cash_ratio"
    category = "quality"
    description = "现金比率"
    def calculate(self, df, **kw): return df.get("cash_ratio", pd.Series(np.nan, index=df.index))

class _OperatingEfficiency(FactorBase):
    name = "operating_efficiency"
    category = "quality"
    description = "运营效率"
    def calculate(self, df, **kw):
        rev = df.get("total_revenue", pd.Series(np.nan, index=df.index))
        sell = df.get("sell_exp", pd.Series(np.nan, index=df.index))
        admin = df.get("admin_exp", pd.Series(np.nan, index=df.index))
        return (sell + admin) / rev.replace(0, np.nan)
