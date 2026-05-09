import pandas as pd
import numpy as np
from .base import FactorBase
from .registry import FactorRegistry


class SentimentFactors:
    @staticmethod
    def register_all():
        FactorRegistry.register(_NorthFlow())
        FactorRegistry.register(_NorthFlowMA5())
        FactorRegistry.register(_MarginBuyRatio())
        FactorRegistry.register(_ShortSellRatio())
        FactorRegistry.register(_MoneyFlowNet())
        FactorRegistry.register(_MoneyFlowMA5())
        FactorRegistry.register(_LargeBuyRatio())
        FactorRegistry.register(_SmallBuyRatio())
        FactorRegistry.register(_NewsSentiment())
        FactorRegistry.register(_NewsCount())
        FactorRegistry.register(_NewsImpactScore())
        FactorRegistry.register(_DragonTigerNet())
        FactorRegistry.register(_BlockTradePremium())
        FactorRegistry.register(_MarginBalanceChange())
        FactorRegistry.register(_NetMFPerCap())


class _NorthFlow(FactorBase):
    name = "north_flow"
    category = "sentiment"
    description = "北向资金净流入"
    def calculate(self, df, **kw): return df.get("north_net", pd.Series(np.nan, index=df.index))

class _NorthFlowMA5(FactorBase):
    name = "north_flow_ma5"
    category = "sentiment"
    description = "5日北向资金均值"
    def calculate(self, df, **kw):
        return df.get("north_net", pd.Series(np.nan, index=df.index)).rolling(5).mean()

class _MarginBuyRatio(FactorBase):
    name = "margin_buy_ratio"
    category = "sentiment"
    description = "融资买入占比"
    def calculate(self, df, **kw): return df.get("rz_buy_ratio", pd.Series(np.nan, index=df.index))

class _ShortSellRatio(FactorBase):
    name = "short_sell_ratio"
    category = "sentiment"
    description = "融券卖出占比"
    def calculate(self, df, **kw): return df.get("rq_sell_ratio", pd.Series(np.nan, index=df.index))

class _MoneyFlowNet(FactorBase):
    name = "money_flow_net"
    category = "sentiment"
    description = "主力资金净流入"
    def calculate(self, df, **kw): return df.get("net_mf_amount", pd.Series(np.nan, index=df.index))

class _MoneyFlowMA5(FactorBase):
    name = "money_flow_ma5"
    category = "sentiment"
    description = "5日主力资金均值"
    def calculate(self, df, **kw):
        return df.get("net_mf_amount", pd.Series(np.nan, index=df.index)).rolling(5).mean()

class _LargeBuyRatio(FactorBase):
    name = "large_buy_ratio"
    category = "sentiment"
    description = "大单买入占比"
    def calculate(self, df, **kw):
        buy_lg = df.get("buy_lg_amount", pd.Series(np.nan, index=df.index))
        sell_lg = df.get("sell_lg_amount", pd.Series(np.nan, index=df.index))
        total = buy_lg + sell_lg
        return buy_lg / total.replace(0, np.nan)

class _SmallBuyRatio(FactorBase):
    name = "small_buy_ratio"
    category = "sentiment"
    description = "小单买入占比"
    def calculate(self, df, **kw):
        buy_sm = df.get("buy_sm_amount", pd.Series(np.nan, index=df.index))
        sell_sm = df.get("sell_sm_amount", pd.Series(np.nan, index=df.index))
        total = buy_sm + sell_sm
        return buy_sm / total.replace(0, np.nan)

class _NewsSentiment(FactorBase):
    name = "news_sentiment"
    category = "sentiment"
    description = "NLP舆情情感得分"
    def calculate(self, df, **kw): return df.get("news_sentiment_score", pd.Series(np.nan, index=df.index))

class _NewsCount(FactorBase):
    name = "news_count"
    category = "sentiment"
    description = "新闻数量"
    def calculate(self, df, **kw): return df.get("news_count", pd.Series(0, index=df.index))

class _NewsImpactScore(FactorBase):
    name = "news_impact_score"
    category = "sentiment"
    description = "新闻影响力评分"
    def calculate(self, df, **kw): return df.get("impact_score", pd.Series(np.nan, index=df.index))

class _DragonTigerNet(FactorBase):
    name = "dragon_tiger_net"
    category = "sentiment"
    description = "龙虎榜净买入"
    def calculate(self, df, **kw): return df.get("lhb_net", pd.Series(np.nan, index=df.index))

class _BlockTradePremium(FactorBase):
    name = "block_trade_premium"
    category = "sentiment"
    description = "大宗交易溢价"
    def calculate(self, df, **kw): return df.get("block_premium", pd.Series(np.nan, index=df.index))

class _MarginBalanceChange(FactorBase):
    name = "margin_balance_change"
    category = "sentiment"
    description = "融资余额变化率"
    def calculate(self, df, **kw):
        rz = df.get("rz_ye", pd.Series(np.nan, index=df.index))
        return rz.pct_change(5, fill_method=None)

class _NetMFPerCap(FactorBase):
    name = "net_mf_per_cap"
    category = "sentiment"
    description = "人均主力净流入"
    def calculate(self, df, **kw):
        nmf = df.get("net_mf_amount", pd.Series(np.nan, index=df.index))
        vol = df.get("vol", pd.Series(np.nan, index=df.index))
        return nmf / vol.replace(0, np.nan)
