from typing import Dict, Type, List
from loguru import logger
from .base import FactorBase


class FactorRegistry:
    _factors: Dict[str, FactorBase] = {}

    @classmethod
    def register(cls, factor: FactorBase):
        cls._factors[factor.name] = factor
        return factor

    @classmethod
    def get(cls, name: str) -> FactorBase:
        return cls._factors.get(name)

    @classmethod
    def all_factors(cls) -> Dict[str, FactorBase]:
        return dict(cls._factors)

    @classmethod
    def by_category(cls, category: str) -> Dict[str, FactorBase]:
        return {k: v for k, v in cls._factors.items() if v.category == category}

    @classmethod
    def factor_names(cls) -> List[str]:
        return list(cls._factors.keys())

    @classmethod
    def count(cls) -> int:
        return len(cls._factors)
