import pandas as pd
import numpy as np
from .base import FactorBase
from .registry import FactorRegistry


class AlternativeFactors:
    @staticmethod
    def register_all():
        FactorRegistry.register(_MarginBalanceRatio())
        FactorRegistry.register(_MarginBuySellDiff())
        FactorRegistry.register(_ShortInterestRatio())
        FactorRegistry.register(_RepurchaseRatio())
        FactorRegistry.register(_InsiderBuyRatio())
        FactorRegistry.register(_ShareholderChange())
        FactorRegistry.register(_InstHoldRatio())
        FactorRegistry.register(_InstHoldChange())
        FactorRegistry.register(_UnlockRatio())
        FactorRegistry.register(_STFlag())
        FactorRegistry.register(_ListAge())
        FactorRegistry.register(_IndustryPEGap())
        FactorRegistry.register(_CrossSectionMomentum())
        FactorRegistry.register(_Illiquidity())
        FactorRegistry.register(_AmihudIlliquidity())
        FactorRegistry.register(_Betas())
        FactorRegistry.register(_IdioVol())
        FactorRegistry.register(_MaxDailyReturn())
        FactorRegistry.register(_MinDailyReturn())
        FactorRegistry.register(_RealizedVol())


class _MarginBalanceRatio(FactorBase):
    name = "margin_balance_ratio"
    category = "alternative"
    description = "融资余额/市值"
    def calculate(self, df, **kw):
        rz = df.get("rz_ye", pd.Series(np.nan, index=df.index))
        mv = df.get("total_mv", pd.Series(np.nan, index=df.index))
        return rz / mv.replace(0, np.nan)

class _MarginBuySellDiff(FactorBase):
    name = "margin_buysell_diff"
    category = "alternative"
    description = "融资买入-偿还差额"
    def calculate(self, df, **kw): return df.get("rz_buysell_diff", pd.Series(np.nan, index=df.index))

class _ShortInterestRatio(FactorBase):
    name = "short_interest_ratio"
    category = "alternative"
    description = "融券余量/流通股"
    def calculate(self, df, **kw): return df.get("rq_ratio", pd.Series(np.nan, index=df.index))

class _RepurchaseRatio(FactorBase):
    name = "repurchase_ratio"
    category = "alternative"
    description = "回购比例"
    def calculate(self, df, **kw): return df.get("repurchase_ratio", pd.Series(np.nan, index=df.index))

class _InsiderBuyRatio(FactorBase):
    name = "insider_buy_ratio"
    category = "alternative"
    description = "内部人买入比"
    def calculate(self, df, **kw): return df.get("insider_buy_ratio", pd.Series(np.nan, index=df.index))

class _ShareholderChange(FactorBase):
    name = "shareholder_change"
    category = "alternative"
    description = "股东数变化率"
    def calculate(self, df, **kw): return df.get("holder_change", pd.Series(np.nan, index=df.index))

class _InstHoldRatio(FactorBase):
    name = "inst_hold_ratio"
    category = "alternative"
    description = "机构持仓比"
    def calculate(self, df, **kw): return df.get("inst_hold_ratio", pd.Series(np.nan, index=df.index))

class _InstHoldChange(FactorBase):
    name = "inst_hold_change"
    category = "alternative"
    description = "机构持仓变化"
    def calculate(self, df, **kw): return df.get("inst_hold_change", pd.Series(np.nan, index=df.index))

class _UnlockRatio(FactorBase):
    name = "unlock_ratio"
    category = "alternative"
    description = "解禁比例"
    def calculate(self, df, **kw): return df.get("unlock_ratio", pd.Series(np.nan, index=df.index))

class _STFlag(FactorBase):
    name = "st_flag"
    category = "alternative"
    description = "ST标记"
    def calculate(self, df, **kw): return df.get("is_st", pd.Series(0, index=df.index))

class _ListAge(FactorBase):
    name = "list_age"
    category = "alternative"
    description = "上市天数"
    def calculate(self, df, **kw): return df.get("list_days", pd.Series(np.nan, index=df.index))

class _IndustryPEGap(FactorBase):
    name = "industry_pe_gap"
    category = "alternative"
    description = "行业PE偏离度"
    def calculate(self, df, **kw): return df.get("industry_pe_gap", pd.Series(np.nan, index=df.index))

class _CrossSectionMomentum(FactorBase):
    name = "cross_section_mom"
    category = "alternative"
    description = "截面动量"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index))
        return ret.rolling(20).sum().rank(pct=True)

class _Illiquidity(FactorBase):
    name = "illiquidity"
    category = "alternative"
    description = "非流动性指标"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index)).abs()
        vol = df.get("vol", pd.Series(np.nan, index=df.index))
        return (ret / vol.replace(0, np.nan)).rolling(20).mean()

class _AmihudIlliquidity(FactorBase):
    name = "amihud_illiquidity"
    category = "alternative"
    description = "Amihud非流动性"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index)).abs()
        amt = df.get("amount", pd.Series(np.nan, index=df.index))
        return (ret / amt.replace(0, np.nan) * 1e6).rolling(20).mean()

class _Betas(FactorBase):
    name = "beta"
    category = "alternative"
    description = "Beta系数"
    def calculate(self, df, **kw): return df.get("beta_60", pd.Series(np.nan, index=df.index))

class _IdioVol(FactorBase):
    name = "idio_vol"
    category = "alternative"
    description = "特质波动率"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index))
        mkt = df.get("market_ret", pd.Series(0, index=df.index))
        residual = ret - mkt
        return residual.rolling(60).std()

class _MaxDailyReturn(FactorBase):
    name = "max_daily_ret"
    category = "alternative"
    description = "最大日收益"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index))
        return ret.rolling(20).max()

class _MinDailyReturn(FactorBase):
    name = "min_daily_ret"
    category = "alternative"
    description = "最小日收益"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index))
        return ret.rolling(20).min()

class _RealizedVol(FactorBase):
    name = "realized_vol"
    category = "alternative"
    description = "已实现波动率"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index)) / 100
        return np.sqrt((ret ** 2).rolling(20).sum())
