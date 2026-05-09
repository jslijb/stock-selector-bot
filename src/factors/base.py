from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd
import numpy as np


class FactorBase(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        pass

    @property
    def description(self) -> str:
        return ""

    @abstractmethod
    def calculate(self, df: pd.DataFrame, **kwargs) -> pd.Series:
        pass

    def winsorize_mad(self, series: pd.Series, n: float = 3.0) -> pd.Series:
        median = series.median()
        mad = (series - median).abs().median() * 1.4826
        lower = median - n * mad
        upper = median + n * mad
        return series.clip(lower, upper)

    def zscore(self, series: pd.Series) -> pd.Series:
        std = series.std()
        if std == 0 or pd.isna(std):
            return pd.Series(0.0, index=series.index)
        return (series - series.mean()) / std

    def rank_normalize(self, series: pd.Series) -> pd.Series:
        return series.rank(pct=True) * 2 - 1
