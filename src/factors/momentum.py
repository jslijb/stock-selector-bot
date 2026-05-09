import pandas as pd
import numpy as np
from .base import FactorBase
from .registry import FactorRegistry


class MomentumFactors:
    @staticmethod
    def register_all():
        for d in [1, 3, 5, 10, 20, 60, 120, 252]:
            FactorRegistry.register(_ReturnN(d))
        FactorRegistry.register(_MomentumReversal5_20())
        FactorRegistry.register(_MomentumReversal20_60())
        FactorRegistry.register(_MomentumReversal60_252())
        FactorRegistry.register(_VolumeRatio5_20())
        FactorRegistry.register(_VolumeRatio20_60())
        FactorRegistry.register(_TurnoverRate())
        FactorRegistry.register(_TurnoverMA5())
        FactorRegistry.register(_TurnoverMA20())
        FactorRegistry.register(_Amplitude())
        FactorRegistry.register(_AmplitudeMA5())
        FactorRegistry.register(_MaxReturn20())
        FactorRegistry.register(_MinReturn20())
        FactorRegistry.register(_Skewness20())
        FactorRegistry.register(_Kurtosis20())
        FactorRegistry.register(_UpRatio20())
        FactorRegistry.register(_VolumeWeightedReturn())
        FactorRegistry.register(_PricePosition20())
        FactorRegistry.register(_PricePosition60())
        FactorRegistry.register(_AbnormalVolume())


class _ReturnN(FactorBase):
    def __init__(self, n):
        self._n = n
    @property
    def name(self): return f"return_{self._n}d"
    @property
    def category(self): return "momentum"
    @property
    def description(self): return f"{self._n}日收益率"
    def calculate(self, df, **kw):
        close = df.get("close", pd.Series(np.nan, index=df.index))
        return close.pct_change(self._n, fill_method=None)


class _MomentumReversal5_20(FactorBase):
    name = "mom_rev_5_20"
    category = "momentum"
    description = "5日/20日动量反转"
    def calculate(self, df, **kw):
        r5 = df.get("close", pd.Series(np.nan, index=df.index)).pct_change(5, fill_method=None)
        r20 = df.get("close", pd.Series(np.nan, index=df.index)).pct_change(20, fill_method=None)
        return r5 - r20

class _MomentumReversal20_60(FactorBase):
    name = "mom_rev_20_60"
    category = "momentum"
    description = "20日/60日动量反转"
    def calculate(self, df, **kw):
        r20 = df.get("close", pd.Series(np.nan, index=df.index)).pct_change(20, fill_method=None)
        r60 = df.get("close", pd.Series(np.nan, index=df.index)).pct_change(60, fill_method=None)
        return r20 - r60

class _MomentumReversal60_252(FactorBase):
    name = "mom_rev_60_252"
    category = "momentum"
    description = "60日/252日动量反转"
    def calculate(self, df, **kw):
        r60 = df.get("close", pd.Series(np.nan, index=df.index)).pct_change(60, fill_method=None)
        r252 = df.get("close", pd.Series(np.nan, index=df.index)).pct_change(252, fill_method=None)
        return r60 - r252

class _VolumeRatio5_20(FactorBase):
    name = "vol_ratio_5_20"
    category = "momentum"
    description = "5日/20日量比"
    def calculate(self, df, **kw):
        vol = df.get("vol", pd.Series(np.nan, index=df.index))
        ma5 = vol.rolling(5).mean()
        ma20 = vol.rolling(20).mean()
        return ma5 / ma20.replace(0, np.nan)

class _VolumeRatio20_60(FactorBase):
    name = "vol_ratio_20_60"
    category = "momentum"
    description = "20日/60日量比"
    def calculate(self, df, **kw):
        vol = df.get("vol", pd.Series(np.nan, index=df.index))
        ma20 = vol.rolling(20).mean()
        ma60 = vol.rolling(60).mean()
        return ma20 / ma60.replace(0, np.nan)

class _TurnoverRate(FactorBase):
    name = "turnover_rate"
    category = "momentum"
    description = "换手率"
    def calculate(self, df, **kw): return df.get("turnover_rate", pd.Series(np.nan, index=df.index))

class _TurnoverMA5(FactorBase):
    name = "turnover_ma5"
    category = "momentum"
    description = "5日换手率均值"
    def calculate(self, df, **kw):
        return df.get("turnover_rate", pd.Series(np.nan, index=df.index)).rolling(5).mean()

class _TurnoverMA20(FactorBase):
    name = "turnover_ma20"
    category = "momentum"
    description = "20日换手率均值"
    def calculate(self, df, **kw):
        return df.get("turnover_rate", pd.Series(np.nan, index=df.index)).rolling(20).mean()

class _Amplitude(FactorBase):
    name = "amplitude"
    category = "momentum"
    description = "振幅"
    def calculate(self, df, **kw):
        high = df.get("high", pd.Series(np.nan, index=df.index))
        low = df.get("low", pd.Series(np.nan, index=df.index))
        pre = df.get("pre_close", pd.Series(np.nan, index=df.index))
        return (high - low) / pre.replace(0, np.nan)

class _AmplitudeMA5(FactorBase):
    name = "amplitude_ma5"
    category = "momentum"
    description = "5日振幅均值"
    def calculate(self, df, **kw):
        high = df.get("high", pd.Series(np.nan, index=df.index))
        low = df.get("low", pd.Series(np.nan, index=df.index))
        pre = df.get("pre_close", pd.Series(np.nan, index=df.index))
        amp = (high - low) / pre.replace(0, np.nan)
        return amp.rolling(5).mean()

class _MaxReturn20(FactorBase):
    name = "max_return_20"
    category = "momentum"
    description = "20日最大涨幅"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index)) / 100
        return ret.rolling(20).max()

class _MinReturn20(FactorBase):
    name = "min_return_20"
    category = "momentum"
    description = "20日最大跌幅"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index)) / 100
        return ret.rolling(20).min()

class _Skewness20(FactorBase):
    name = "skewness_20"
    category = "momentum"
    description = "20日收益率偏度"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index)) / 100
        return ret.rolling(20).skew()

class _Kurtosis20(FactorBase):
    name = "kurtosis_20"
    category = "momentum"
    description = "20日收益率峰度"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index)) / 100
        return ret.rolling(20).kurt()

class _UpRatio20(FactorBase):
    name = "up_ratio_20"
    category = "momentum"
    description = "20日上涨天数占比"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index))
        up = (ret > 0).astype(float)
        return up.rolling(20).mean()

class _VolumeWeightedReturn(FactorBase):
    name = "vol_weighted_return"
    category = "momentum"
    description = "成交量加权收益"
    def calculate(self, df, **kw):
        ret = df.get("pct_chg", pd.Series(np.nan, index=df.index))
        vol = df.get("vol", pd.Series(np.nan, index=df.index))
        w = vol.rolling(20).mean()
        return (ret * w).rolling(20).sum() / w.rolling(20).sum().replace(0, np.nan)

class _PricePosition20(FactorBase):
    name = "price_position_20"
    category = "momentum"
    description = "20日价格位置"
    def calculate(self, df, **kw):
        close = df.get("close", pd.Series(np.nan, index=df.index))
        low20 = close.rolling(20).min()
        high20 = close.rolling(20).max()
        return (close - low20) / (high20 - low20).replace(0, np.nan)

class _PricePosition60(FactorBase):
    name = "price_position_60"
    category = "momentum"
    description = "60日价格位置"
    def calculate(self, df, **kw):
        close = df.get("close", pd.Series(np.nan, index=df.index))
        low60 = close.rolling(60).min()
        high60 = close.rolling(60).max()
        return (close - low60) / (high60 - low60).replace(0, np.nan)

class _AbnormalVolume(FactorBase):
    name = "abnormal_volume"
    category = "momentum"
    description = "异常成交量"
    def calculate(self, df, **kw):
        vol = df.get("vol", pd.Series(np.nan, index=df.index))
        ma20 = vol.rolling(20).mean()
        std20 = vol.rolling(20).std()
        return (vol - ma20) / std20.replace(0, np.nan)
