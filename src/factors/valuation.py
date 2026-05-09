import pandas as pd
import numpy as np
from .base import FactorBase
from .registry import FactorRegistry


class ValuationFactors:
    @staticmethod
    def register_all():
        FactorRegistry.register(_PE_TTM())
        FactorRegistry.register(_PB())
        FactorRegistry.register(_PS_TTM())
        FactorRegistry.register(_PCF_TTM())
        FactorRegistry.register(_EV_EBITDA())
        FactorRegistry.register(_DividendYield())
        FactorRegistry.register(_PEPercentile())
        FactorRegistry.register(_PBPercentile())
        FactorRegistry.register(_PEG())
        FactorRegistry.register(_MarketCap())
        FactorRegistry.register(_LogMarketCap())
        FactorRegistry.register(_CapToEV())
        FactorRegistry.register(_BookToPrice())
        FactorRegistry.register(_EarningsYield())
        FactorRegistry.register(_CashFlowYield())


class _PE_TTM(FactorBase):
    name = "pe_ttm"
    category = "valuation"
    description = "滚动市盈率"
    def calculate(self, df, **kw): return df.get("pe_ttm", pd.Series(np.nan, index=df.index))

class _PB(FactorBase):
    name = "pb"
    category = "valuation"
    description = "市净率"
    def calculate(self, df, **kw): return df.get("pb", pd.Series(np.nan, index=df.index))

class _PS_TTM(FactorBase):
    name = "ps_ttm"
    category = "valuation"
    description = "滚动市销率"
    def calculate(self, df, **kw): return df.get("ps_ttm", pd.Series(np.nan, index=df.index))

class _PCF_TTM(FactorBase):
    name = "pcf_ttm"
    category = "valuation"
    description = "滚动市现率"
    def calculate(self, df, **kw): return df.get("pcf_ttm", pd.Series(np.nan, index=df.index))

class _EV_EBITDA(FactorBase):
    name = "ev_ebitda"
    category = "valuation"
    description = "企业价值倍数"
    def calculate(self, df, **kw):
        ev = df.get("total_assets", pd.Series(np.nan, index=df.index)) - df.get("total_liab", pd.Series(np.nan, index=df.index))
        ebitda = df.get("total_revenue", pd.Series(np.nan, index=df.index)) - df.get("total_cogs", pd.Series(np.nan, index=df.index))
        return ev / ebitda.replace(0, np.nan)

class _DividendYield(FactorBase):
    name = "dividend_yield"
    category = "valuation"
    description = "股息率"
    def calculate(self, df, **kw): return df.get("dv_ratio", pd.Series(np.nan, index=df.index))

class _PEPercentile(FactorBase):
    name = "pe_percentile"
    category = "valuation"
    description = "PE历史分位数"
    def calculate(self, df, **kw):
        pe = df.get("pe_ttm", pd.Series(np.nan, index=df.index))
        return pe.rank(pct=True)

class _PBPercentile(FactorBase):
    name = "pb_percentile"
    category = "valuation"
    description = "PB历史分位数"
    def calculate(self, df, **kw):
        pb = df.get("pb", pd.Series(np.nan, index=df.index))
        return pb.rank(pct=True)

class _PEG(FactorBase):
    name = "peg"
    category = "valuation"
    description = "PEG比率"
    def calculate(self, df, **kw):
        pe = df.get("pe_ttm", pd.Series(np.nan, index=df.index))
        g = df.get("np_yoys", pd.Series(np.nan, index=df.index)) / 100
        return pe / g.replace(0, np.nan)

class _MarketCap(FactorBase):
    name = "market_cap"
    category = "valuation"
    description = "总市值"
    def calculate(self, df, **kw): return df.get("total_mv", pd.Series(np.nan, index=df.index))

class _LogMarketCap(FactorBase):
    name = "log_market_cap"
    category = "valuation"
    description = "对数市值"
    def calculate(self, df, **kw):
        mc = df.get("total_mv", pd.Series(np.nan, index=df.index))
        return np.log(mc.mask(mc <= 0, np.nan))

class _CapToEV(FactorBase):
    name = "cap_to_ev"
    category = "valuation"
    description = "市值/企业价值"
    def calculate(self, df, **kw):
        mc = df.get("total_mv", pd.Series(np.nan, index=df.index))
        ev = mc + df.get("total_liab", pd.Series(0, index=df.index)) - df.get("total_hldr_eqy", pd.Series(0, index=df.index))
        return mc / ev.replace(0, np.nan)

class _BookToPrice(FactorBase):
    name = "book_to_price"
    category = "valuation"
    description = "账面价值/价格"
    def calculate(self, df, **kw):
        pb = df.get("pb", pd.Series(np.nan, index=df.index))
        return 1.0 / pb.replace(0, np.nan)

class _EarningsYield(FactorBase):
    name = "earnings_yield"
    category = "valuation"
    description = "盈利收益率"
    def calculate(self, df, **kw):
        pe = df.get("pe_ttm", pd.Series(np.nan, index=df.index))
        return 1.0 / pe.replace(0, np.nan)

class _CashFlowYield(FactorBase):
    name = "cashflow_yield"
    category = "valuation"
    description = "现金流收益率"
    def calculate(self, df, **kw):
        pcf = df.get("pcf_ttm", pd.Series(np.nan, index=df.index))
        return 1.0 / pcf.replace(0, np.nan)
