import pandas as pd
import numpy as np
from .base import FactorBase
from .registry import FactorRegistry


class TechnicalFactors:
    @staticmethod
    def register_all():
        FactorRegistry.register(_MA5())
        FactorRegistry.register(_MA10())
        FactorRegistry.register(_MA20())
        FactorRegistry.register(_MA60())
        FactorRegistry.register(_MA5Bias())
        FactorRegistry.register(_MA20Bias())
        FactorRegistry.register(_MACD())
        FactorRegistry.register(_MACDSignal())
        FactorRegistry.register(_MACDHist())
        FactorRegistry.register(_RSI6())
        FactorRegistry.register(_RSI12())
        FactorRegistry.register(_RSI24())
        FactorRegistry.register(_KDJ_K())
        FactorRegistry.register(_KDJ_D())
        FactorRegistry.register(_KDJ_J())
        FactorRegistry.register(_BOLLPosition())
        FactorRegistry.register(_ATR14())
        FactorRegistry.register(_ADX14())
        FactorRegistry.register(_OBVChange())
        FactorRegistry.register(_WMA20())
        FactorRegistry.register(_EMA12())
        FactorRegistry.register(_EMA26())
        FactorRegistry.register(_VWAP20())
        FactorRegistry.register(_IchimokuSpanA())
        FactorRegistry.register(_IchimokuSpanB())
        FactorRegistry.register(_DonchianWidth())
        FactorRegistry.register(_PivotPoint())
        FactorRegistry.register(_GapRatio())
        FactorRegistry.register(_UpperShadowRatio())
        FactorRegistry.register(_LowerShadowRatio())
        FactorRegistry.register(_BodyRatio())


def _sma(series, n):
    return series.rolling(n).mean()

def _ema(series, n):
    return series.ewm(span=n, adjust=False).mean()

class _MA5(FactorBase):
    name = "ma5"
    category = "technical"
    description = "5日均线"
    def calculate(self, df, **kw): return _sma(df.get("close", pd.Series(np.nan, index=df.index)), 5)

class _MA10(FactorBase):
    name = "ma10"
    category = "technical"
    description = "10日均线"
    def calculate(self, df, **kw): return _sma(df.get("close", pd.Series(np.nan, index=df.index)), 10)

class _MA20(FactorBase):
    name = "ma20"
    category = "technical"
    description = "20日均线"
    def calculate(self, df, **kw): return _sma(df.get("close", pd.Series(np.nan, index=df.index)), 20)

class _MA60(FactorBase):
    name = "ma60"
    category = "technical"
    description = "60日均线"
    def calculate(self, df, **kw): return _sma(df.get("close", pd.Series(np.nan, index=df.index)), 60)

class _MA5Bias(FactorBase):
    name = "ma5_bias"
    category = "technical"
    description = "5日乖离率"
    def calculate(self, df, **kw):
        c = df.get("close", pd.Series(np.nan, index=df.index))
        return (c - _sma(c, 5)) / _sma(c, 5).replace(0, np.nan)

class _MA20Bias(FactorBase):
    name = "ma20_bias"
    category = "technical"
    description = "20日乖离率"
    def calculate(self, df, **kw):
        c = df.get("close", pd.Series(np.nan, index=df.index))
        return (c - _sma(c, 20)) / _sma(c, 20).replace(0, np.nan)

class _MACD(FactorBase):
    name = "macd_dif"
    category = "technical"
    description = "MACD DIF"
    def calculate(self, df, **kw):
        c = df.get("close", pd.Series(np.nan, index=df.index))
        return _ema(c, 12) - _ema(c, 26)

class _MACDSignal(FactorBase):
    name = "macd_signal"
    category = "technical"
    description = "MACD信号线"
    def calculate(self, df, **kw):
        c = df.get("close", pd.Series(np.nan, index=df.index))
        dif = _ema(c, 12) - _ema(c, 26)
        return _ema(dif, 9)

class _MACDHist(FactorBase):
    name = "macd_hist"
    category = "technical"
    description = "MACD柱状"
    def calculate(self, df, **kw):
        c = df.get("close", pd.Series(np.nan, index=df.index))
        dif = _ema(c, 12) - _ema(c, 26)
        dea = _ema(dif, 9)
        return 2 * (dif - dea)

class _RSI6(FactorBase):
    name = "rsi_6"
    category = "technical"
    description = "6日RSI"
    def calculate(self, df, **kw): return _calc_rsi(df, 6)

class _RSI12(FactorBase):
    name = "rsi_12"
    category = "technical"
    description = "12日RSI"
    def calculate(self, df, **kw): return _calc_rsi(df, 12)

class _RSI24(FactorBase):
    name = "rsi_24"
    category = "technical"
    description = "24日RSI"
    def calculate(self, df, **kw): return _calc_rsi(df, 24)

def _calc_rsi(df, n):
    chg = df.get("pct_chg", pd.Series(np.nan, index=df.index))
    gain = chg.clip(lower=0)
    loss = (-chg).clip(lower=0)
    avg_gain = gain.rolling(n).mean()
    avg_loss = loss.rolling(n).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

class _KDJ_K(FactorBase):
    name = "kdj_k"
    category = "technical"
    description = "KDJ K值"
    def calculate(self, df, **kw): return _calc_kdj(df)[0]

class _KDJ_D(FactorBase):
    name = "kdj_d"
    category = "technical"
    description = "KDJ D值"
    def calculate(self, df, **kw): return _calc_kdj(df)[1]

class _KDJ_J(FactorBase):
    name = "kdj_j"
    category = "technical"
    description = "KDJ J值"
    def calculate(self, df, **kw): return _calc_kdj(df)[2]

def _calc_kdj(df):
    low = df.get("low", pd.Series(np.nan, index=df.index))
    high = df.get("high", pd.Series(np.nan, index=df.index))
    close = df.get("close", pd.Series(np.nan, index=df.index))
    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9).replace(0, np.nan) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d
    return k, d, j

class _BOLLPosition(FactorBase):
    name = "boll_position"
    category = "technical"
    description = "布林带位置"
    def calculate(self, df, **kw):
        c = df.get("close", pd.Series(np.nan, index=df.index))
        ma = _sma(c, 20)
        std = c.rolling(20).std()
        return (c - ma) / (2 * std).replace(0, np.nan)

class _ATR14(FactorBase):
    name = "atr_14"
    category = "technical"
    description = "14日ATR"
    def calculate(self, df, **kw):
        high = df.get("high", pd.Series(np.nan, index=df.index))
        low = df.get("low", pd.Series(np.nan, index=df.index))
        pre_close = df.get("pre_close", pd.Series(np.nan, index=df.index))
        tr = pd.concat([high - low, (high - pre_close).abs(), (low - pre_close).abs()], axis=1).max(axis=1)
        return tr.rolling(14).mean()

class _ADX14(FactorBase):
    name = "adx_14"
    category = "technical"
    description = "14日ADX"
    def calculate(self, df, **kw): return df.get("adx_14", pd.Series(np.nan, index=df.index))

class _OBVChange(FactorBase):
    name = "obv_change"
    category = "technical"
    description = "OBV变化率"
    def calculate(self, df, **kw):
        close = df.get("close", pd.Series(np.nan, index=df.index))
        vol = df.get("vol", pd.Series(np.nan, index=df.index))
        sign = np.sign(close.diff())
        obv = (sign * vol).cumsum()
        return obv.pct_change(5, fill_method=None)

class _WMA20(FactorBase):
    name = "wma20"
    category = "technical"
    description = "20日加权均线"
    def calculate(self, df, **kw):
        c = df.get("close", pd.Series(np.nan, index=df.index))
        weights = np.arange(1, 21)
        return c.rolling(20).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

class _EMA12(FactorBase):
    name = "ema12"
    category = "technical"
    description = "12日EMA"
    def calculate(self, df, **kw): return _ema(df.get("close", pd.Series(np.nan, index=df.index)), 12)

class _EMA26(FactorBase):
    name = "ema26"
    category = "technical"
    description = "26日EMA"
    def calculate(self, df, **kw): return _ema(df.get("close", pd.Series(np.nan, index=df.index)), 26)

class _VWAP20(FactorBase):
    name = "vwap20"
    category = "technical"
    description = "20日成交量加权均价"
    def calculate(self, df, **kw):
        c = df.get("close", pd.Series(np.nan, index=df.index))
        v = df.get("vol", pd.Series(np.nan, index=df.index))
        return (c * v).rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)

class _IchimokuSpanA(FactorBase):
    name = "ichimoku_span_a"
    category = "technical"
    description = "一目均衡表SpanA"
    def calculate(self, df, **kw):
        c = df.get("close", pd.Series(np.nan, index=df.index))
        h = df.get("high", pd.Series(np.nan, index=df.index))
        l = df.get("low", pd.Series(np.nan, index=df.index))
        conv = (h.rolling(9).max() + l.rolling(9).min()) / 2
        base = (h.rolling(26).max() + l.rolling(26).min()) / 2
        return (conv + base) / 2

class _IchimokuSpanB(FactorBase):
    name = "ichimoku_span_b"
    category = "technical"
    description = "一目均衡表SpanB"
    def calculate(self, df, **kw):
        h = df.get("high", pd.Series(np.nan, index=df.index))
        l = df.get("low", pd.Series(np.nan, index=df.index))
        return (h.rolling(52).max() + l.rolling(52).min()) / 2

class _DonchianWidth(FactorBase):
    name = "donchian_width"
    category = "technical"
    description = "唐奇安通道宽度"
    def calculate(self, df, **kw):
        h = df.get("high", pd.Series(np.nan, index=df.index))
        l = df.get("low", pd.Series(np.nan, index=df.index))
        c = df.get("close", pd.Series(np.nan, index=df.index))
        return (h.rolling(20).max() - l.rolling(20).min()) / c.replace(0, np.nan)

class _PivotPoint(FactorBase):
    name = "pivot_point"
    category = "technical"
    description = "枢轴点"
    def calculate(self, df, **kw):
        h = df.get("high", pd.Series(np.nan, index=df.index))
        l = df.get("low", pd.Series(np.nan, index=df.index))
        c = df.get("close", pd.Series(np.nan, index=df.index))
        return (h + l + c) / 3

class _GapRatio(FactorBase):
    name = "gap_ratio"
    category = "technical"
    description = "跳空比率"
    def calculate(self, df, **kw):
        o = df.get("open", pd.Series(np.nan, index=df.index))
        pre = df.get("pre_close", pd.Series(np.nan, index=df.index))
        return (o - pre) / pre.replace(0, np.nan)

class _UpperShadowRatio(FactorBase):
    name = "upper_shadow_ratio"
    category = "technical"
    description = "上影线比率"
    def calculate(self, df, **kw):
        h = df.get("high", pd.Series(np.nan, index=df.index))
        o = df.get("open", pd.Series(np.nan, index=df.index))
        c = df.get("close", pd.Series(np.nan, index=df.index))
        body_top = pd.concat([o, c], axis=1).max(axis=1)
        body = (c - o).abs()
        return (h - body_top) / body.replace(0, np.nan)

class _LowerShadowRatio(FactorBase):
    name = "lower_shadow_ratio"
    category = "technical"
    description = "下影线比率"
    def calculate(self, df, **kw):
        l = df.get("low", pd.Series(np.nan, index=df.index))
        o = df.get("open", pd.Series(np.nan, index=df.index))
        c = df.get("close", pd.Series(np.nan, index=df.index))
        body_bot = pd.concat([o, c], axis=1).min(axis=1)
        body = (c - o).abs()
        return (body_bot - l) / body.replace(0, np.nan)

class _BodyRatio(FactorBase):
    name = "body_ratio"
    category = "technical"
    description = "实体比率"
    def calculate(self, df, **kw):
        o = df.get("open", pd.Series(np.nan, index=df.index))
        c = df.get("close", pd.Series(np.nan, index=df.index))
        h = df.get("high", pd.Series(np.nan, index=df.index))
        l = df.get("low", pd.Series(np.nan, index=df.index))
        return (c - o).abs() / (h - l).replace(0, np.nan)
