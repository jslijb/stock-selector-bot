import numpy as np
import pandas as pd
from loguru import logger
from typing import Dict, List, Optional
from ..config import get_config
from ..data.db import Database


class RiskManager:
    def __init__(self, db: Optional[Database] = None):
        self.cfg = get_config()
        self.db = db or Database.get_instance(self.cfg.duckdb_path)

    def validate_and_adjust(self, holdings: List[Dict], industry_map: Optional[Dict[str, str]] = None) -> Dict:
        max_w = self.cfg.risk.max_single_weight
        max_dev = self.cfg.risk.industry_deviation

        adjusted = []
        for h in holdings:
            ts_code = h["ts_code"]
            weight = h.get("weight", 0)
            if weight > max_w:
                logger.warning(f"{ts_code} 权重 {weight:.2%} 超限，截断至 {max_w:.2%}")
                weight = max_w
            adjusted.append({**h, "weight": weight})

        total = sum(h["weight"] for h in adjusted)
        if total > 0:
            for h in adjusted:
                h["weight"] = h["weight"] / total

        if industry_map is not None:
            adjusted = self._check_industry_deviation(adjusted, industry_map, max_dev)

        total = sum(h["weight"] for h in adjusted)
        if abs(total - 1.0) > 0.001:
            for h in adjusted:
                h["weight"] = h["weight"] / total

        violations = self._check_violations(adjusted, industry_map, max_w, max_dev)
        return {
            "holdings": adjusted,
            "total_weight": sum(h["weight"] for h in adjusted),
            "violations": violations,
            "is_valid": len(violations) == 0,
        }

    def _check_industry_deviation(self, holdings: List[Dict], industry_map: Dict[str, str], max_dev: float) -> List[Dict]:
        industry_weights = {}
        total = sum(h["weight"] for h in holdings)
        for h in holdings:
            ind = industry_map.get(h["ts_code"], "unknown")
            industry_weights[ind] = industry_weights.get(ind, 0) + h["weight"]
        if total > 0:
            for ind in industry_weights:
                industry_weights[ind] /= total

        n_industries = len(industry_weights)
        if n_industries == 0:
            return holdings
        benchmark = 1.0 / n_industries

        excess_industries = []
        for ind, w in industry_weights.items():
            if w - benchmark > max_dev:
                excess_industries.append(ind)

        if not excess_industries:
            return holdings

        for ind in excess_industries:
            target = benchmark + max_dev
            excess = industry_weights[ind] - target
            ind_holdings = [h for h in holdings if industry_map.get(h["ts_code"], "unknown") == ind]
            ind_total = sum(h["weight"] for h in ind_holdings)
            if ind_total > 0:
                scale = (ind_total - excess) / ind_total
                for h in holdings:
                    if industry_map.get(h["ts_code"], "unknown") == ind:
                        h["weight"] *= scale

        return holdings

    def _check_violations(self, holdings: List[Dict], industry_map: Optional[Dict], max_w: float, max_dev: float) -> List[str]:
        violations = []
        for h in holdings:
            if h["weight"] > max_w + 0.001:
                violations.append(f"{h['ts_code']} 权重 {h['weight']:.2%} 超过上限 {max_w:.2%}")

        if industry_map is not None:
            industry_weights = {}
            total = sum(h["weight"] for h in holdings)
            for h in holdings:
                ind = industry_map.get(h["ts_code"], "unknown")
                industry_weights[ind] = industry_weights.get(ind, 0) + h["weight"]
            if total > 0:
                n = len(industry_weights)
                benchmark = 1.0 / n if n > 0 else 1.0
                for ind, w in industry_weights.items():
                    if w / total - benchmark > max_dev + 0.001:
                        violations.append(f"行业 {ind} 偏离 {w/total - benchmark:.2%} 超限 {max_dev:.2%}")

        return violations

    def save_decision(self, trade_date: str, holdings: List[Dict], ml_scores: Optional[pd.Series] = None):
        dt = trade_date if len(trade_date) != 8 else f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        for h in holdings:
            ml_score = ml_scores.get(h["ts_code"], 0) if ml_scores is not None else 0
            self.db.execute(
                """INSERT INTO decisions (trade_date, ts_code, weight, score, ml_score, reason)
                VALUES (?, ?, ?, ?, ?, ?)""",
                [dt, h["ts_code"], h["weight"], h.get("score", 0), ml_score, h.get("reason", "")],
            )
        logger.info(f"决策已保存: {trade_date}, {len(holdings)} 只")
