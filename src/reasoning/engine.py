import os
import json
import shap
import numpy as np
import pandas as pd
from loguru import logger
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from openai import OpenAI
from xgboost import XGBRegressor
from sklearn.model_selection import TimeSeriesSplit
from ..config import get_config
from ..data.db import Database
from ..factors.engine import FactorEngine
from ..factors.registry import FactorRegistry
from ..memory.memory import EpisodicMemory


STOCK_SELECTION_PROMPT = """你是量化选股决策引擎。根据以下信息输出选股决策。

## 当前市场环境
{market_env}

## 历史相似时期参考
{historical_ref}

## 精选候选池（共{candidate_count}只）
{candidates}

## 输出要求
从候选池中挑选 {final_n} 只股票，为每只分配权重(weight为0-1之间小数，总和=1.0，单票<={max_weight_pct})。

直接输出JSON，不要输出任何其他文字、解释或markdown标记。以{{开头，以}}结尾。

{{
  "holdings": [
    {{
      "ts_code": "000001.SZ",
      "weight": 0.05,
      "reason": "选择理由"
    }}
  ],
  "market_view": "市场观点",
  "risk_notes": "风险提示"
}}
"""


class ReasoningEngine:
    def __init__(self, db: Optional[Database] = None, factor_engine: Optional[FactorEngine] = None,
                 memory: Optional[EpisodicMemory] = None):
        self.cfg = get_config()
        self.db = db or Database.get_instance(self.cfg.duckdb_path)
        self.factor_engine = factor_engine or FactorEngine(self.db)
        self.memory = memory or EpisodicMemory(self.db)
        self._init_llm_client()

    def _init_llm_client(self):
        self.cfg = get_config()
        api_key = self.cfg.llm.api_key or os.environ.get(self.cfg.llm.api_key_env)
        if api_key:
            import httpx
            self.llm_client = OpenAI(
                api_key=api_key, base_url=self.cfg.llm.base_url,
                max_retries=2, timeout=httpx.Timeout(None, connect=15.0),
            )
        else:
            self.llm_client = None
            logger.warning("LLM客户端未初始化")

        self._ml_model: Optional[XGBRegressor] = None

    def _refresh_llm(self):
        self._init_llm_client()

    def layer1_multifactor_score(self, factor_df: pd.DataFrame, trade_date: str) -> pd.Series:
        logger.info("=== 第一层: 多因子打分 ===")
        weights = self.factor_engine.get_factor_weights(trade_date)
        scores = self.factor_engine.score_stocks(factor_df, weights)
        threshold = scores.quantile(1 - self.cfg.reasoning.layer1_top_pct)
        candidates = scores[scores >= threshold]
        logger.info(f"候选池: {len(candidates)} 只 (top {self.cfg.reasoning.layer1_top_pct:.0%})")
        return scores

    def _build_training_labels(self, trade_date: str, lookback: int = 20, forward_days: int = 5,
                              candidate_codes: Optional[list] = None):
        dt = trade_date if len(trade_date) != 8 else f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        try:
            factor_dates = self.db.fetch_df(
                """SELECT DISTINCT trade_date FROM factors_daily
                WHERE trade_date < ? ORDER BY trade_date DESC LIMIT ?""",
                [dt, lookback],
            )
            if len(factor_dates) < 5:
                return None
            date_list = [str(d)[:10] for d in factor_dates["trade_date"]]
            max_factor_date = factor_dates["trade_date"].max()
            price_end = self.db.fetch_df(
                """SELECT DISTINCT trade_date FROM daily_price
                WHERE trade_date >= ? ORDER BY trade_date LIMIT ?""",
                [max_factor_date, forward_days + 1],
            )
            if price_end.empty:
                return None
            max_date = price_end["trade_date"].max()
            min_date = factor_dates["trade_date"].min()
            price_df = self.db.fetch_df(
                """SELECT ts_code, trade_date, close FROM daily_price
                WHERE trade_date BETWEEN ? AND ? ORDER BY ts_code, trade_date""",
                [min_date, max_date],
            )
            if price_df.empty:
                return None
            price_df = price_df.sort_values(["ts_code", "trade_date"])
            price_df["fwd_close"] = price_df.groupby("ts_code")["close"].shift(-forward_days)
            price_df["fwd_ret"] = price_df["fwd_close"] / price_df["close"] - 1
            ret_map = price_df.dropna(subset=["fwd_ret"]).set_index(["ts_code", "trade_date"])["fwd_ret"]

            all_X = []
            all_y = []
            sample_codes = candidate_codes[:500] if candidate_codes else None
            for i, d in enumerate(date_list):
                if sample_codes:
                    placeholders = ",".join(["?"] * len(sample_codes))
                    fdf = self.db.fetch_df(
                        f"""SELECT ts_code, factor_name, factor_value FROM factors_daily
                        WHERE trade_date = ? AND ts_code IN ({placeholders})""",
                        [d] + sample_codes,
                    )
                else:
                    fdf = self.db.fetch_df(
                        """SELECT ts_code, factor_name, factor_value FROM factors_daily
                        WHERE trade_date = ?""",
                        [d],
                    )
                if fdf.empty:
                    continue
                pivot = fdf.pivot(index="ts_code", columns="factor_name", values="factor_value")
                dt_val = factor_dates["trade_date"].iloc[i]
                pivot.index = pd.MultiIndex.from_tuples([(c, dt_val) for c in pivot.index])
                common = pivot.index.intersection(ret_map.index)
                if len(common) > 0:
                    all_X.append(pivot.loc[common].fillna(0))
                    all_y.append(ret_map.loc[common])

            if not all_X or sum(len(x) for x in all_X) < 100:
                return None
            train_X = pd.concat(all_X, axis=0)
            train_y = pd.concat(all_y, axis=0)
            logger.info(f"训练数据: {len(train_X)} 样本, {train_X.shape[1]} 特征, {len(date_list)} 天")
            return train_X, train_y
        except Exception as e:
            raise RuntimeError(f"训练标签构建失败: {e}") from e

    def layer2_ml_select(self, factor_df: pd.DataFrame, scores: pd.Series,
                         labels: Optional[pd.Series] = None,
                         train_X: Optional[pd.DataFrame] = None,
                         train_y: Optional[pd.Series] = None) -> Tuple[pd.Series, Optional[pd.DataFrame]]:
        logger.info("=== 第二层: ML精选 ===")
        threshold = scores.quantile(1 - self.cfg.reasoning.layer1_top_pct)
        candidate_idx = scores[scores >= threshold].index
        X = factor_df.loc[candidate_idx].fillna(0)
        feature_names = X.columns.tolist()

        can_train = train_X is not None and train_y is not None and len(train_y) > 200
        if can_train:
            common_features = list(set(train_X.columns) & set(X.columns))
            if len(common_features) < 10:
                can_train = False

        if can_train:
            X_train = train_X[common_features].fillna(0)
            y_train = train_y.loc[X_train.index]
            n_splits = min(3, max(2, len(X_train) // 500))
            tscv = TimeSeriesSplit(n_splits=n_splits)
            self._ml_model = XGBRegressor(
                n_estimators=200, max_depth=5, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, random_state=42,
            )
            self._ml_model.fit(X_train, y_train)
            X_pred = X[common_features].fillna(0)
            ml_scores = pd.Series(self._ml_model.predict(X_pred), index=candidate_idx)
            logger.info(f"XGBoost模型训练完成: {len(X_train)} 样本, {len(common_features)} 特征")
        else:
            ml_scores = scores.loc[candidate_idx]
            logger.info("训练样本不足，使用因子得分作为ML得分")

        top_n = min(self.cfg.reasoning.layer2_top_n, len(ml_scores))
        selected = ml_scores.nlargest(top_n)
        logger.info(f"精选池: {len(selected)} 只")

        shap_df = None
        if self._ml_model is not None:
            try:
                explainer = shap.TreeExplainer(self._ml_model)
                shap_values = explainer.shap_values(X.loc[selected.index])
                shap_df = pd.DataFrame(shap_values, columns=feature_names, index=selected.index)
                logger.info("SHAP解释完成")
            except Exception as e:
                raise RuntimeError(f"SHAP计算失败: {e}") from e

        return ml_scores, shap_df

    def layer3_llm_decision(self, trade_date: str, candidates: pd.DataFrame,
                            ml_scores: pd.Series, shap_df: Optional[pd.DataFrame],
                            market_env: str = "", similar_days: Optional[List[Dict]] = None) -> Dict:
        logger.info("=== 第三层: LLM认知决策 ===")
        self._refresh_llm()

        if self.llm_client is None:
            logger.warning("LLM未初始化，返回ML得分Top20")
            top = ml_scores.nlargest(self.cfg.reasoning.layer3_final_n)
            return {
                "holdings": [{"ts_code": code, "weight": 1.0/len(top), "reason": "ML精选"} for code in top.index],
                "market_view": "LLM未启用",
                "risk_notes": "",
            }

        if similar_days is None:
            similar_days = self.memory.retrieve_similar(trade_date, top_k=3)

        candidates_text = self._format_candidates(candidates, ml_scores, shap_df)
        historical_text = self._format_historical(similar_days)

        prompt = STOCK_SELECTION_PROMPT.format(
            market_env=market_env or f"交易日期: {trade_date}",
            historical_ref=historical_text,
            candidate_count=len(candidates),
            candidates=candidates_text,
            final_n=self.cfg.reasoning.layer3_final_n,
            max_weight_pct=self.cfg.risk.max_single_weight,
        )

        try:
            import httpx
            timeout_obj = httpx.Timeout(None, connect=15.0)
            resp = self.llm_client.chat.completions.create(
                model=self.cfg.llm.model,
                messages=[
                    {"role": "system", "content": "你是一位专业的量化投资经理，擅长价值与成长结合的投资策略。"},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=self.cfg.llm.max_tokens,
                temperature=self.cfg.llm.temperature,
                timeout=timeout_obj,
            )
            text = resp.choices[0].message.content.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            if not text:
                raise RuntimeError("LLM返回空内容")
            if resp.choices[0].finish_reason == "length":
                raise RuntimeError("LLM输出被max_tokens截断，JSON不完整，请增大max_tokens或简化prompt")
            brace_start = text.find("{")
            if brace_start < 0:
                raise RuntimeError(f"LLM输出不含JSON: {text[:200]}")
            if brace_start > 0:
                logger.warning(f"LLM在JSON前输出了{brace_start}字符非JSON内容，已截取")
                text = text[brace_start:]
            result = json.loads(text)
            if "holdings" not in result or not result["holdings"]:
                raise RuntimeError("LLM返回JSON无holdings字段")
            for h in result["holdings"]:
                if not isinstance(h.get("weight"), (int, float)) or h["weight"] <= 0 or h["weight"] > 1:
                    raise RuntimeError(f"LLM返回异常权重: {h}")
            logger.info(f"LLM选股完成: {len(result.get('holdings', []))} 只")
            return result
        except (json.JSONDecodeError, RuntimeError) as e:
            logger.error(f"LLM决策失败: {e}")
            raise

    def _format_candidates(self, candidates: pd.DataFrame, ml_scores: pd.Series,
                           shap_df: Optional[pd.DataFrame]) -> str:
        lines = []
        for i, (idx, row) in enumerate(candidates.iterrows()):
            line = f"{i+1}. {idx}"
            if idx in ml_scores.index:
                line += f" | ML得分: {ml_scores[idx]:.4f}"
            if shap_df is not None and idx in shap_df.index:
                top_factors = shap_df.loc[idx].abs().nlargest(3)
                line += f" | 关键因子: {', '.join(top_factors.index.tolist())}"
            lines.append(line)
        return "\n".join(lines)

    def _format_historical(self, similar_days: List[Dict]) -> str:
        if not similar_days:
            return "无历史相似时期数据"
        lines = []
        for d in similar_days:
            line = f"- {d['trade_date']} (相似度: {d.get('similarity', 0):.2%})"
            line += f": {d.get('description', '')}"
            hist_dec = self.memory.get_historical_decision(d["trade_date"])
            if hist_dec:
                holdings = [h["ts_code"] for h in hist_dec["holdings"][:5]]
                line += f" | 当时持仓: {', '.join(holdings)}"
            perf = self.memory.get_performance_after(d["trade_date"])
            if perf:
                rets = [p["return_5d"] for p in perf["performance"] if p.get("return_5d") is not None]
                if rets:
                    line += f" | 5日平均收益: {np.mean(rets):.2%}"
            lines.append(line)
        return "\n".join(lines)

    def run_full_pipeline(self, trade_date: str, factor_df: pd.DataFrame,
                          market_env: str = "") -> Dict:
        scores = self.layer1_multifactor_score(factor_df, trade_date)
        candidate_codes = factor_df.index.tolist()
        train_data = self._build_training_labels(trade_date, candidate_codes=candidate_codes)
        train_X, train_y = None, None
        if train_data is not None:
            train_X, train_y = train_data
        ml_scores, shap_df = self.layer2_ml_select(factor_df, scores, train_X=train_X, train_y=train_y)
        selected_idx = ml_scores.nlargest(self.cfg.reasoning.layer2_top_n).index
        candidates_df = factor_df.loc[selected_idx]
        decision = self.layer3_llm_decision(trade_date, candidates_df, ml_scores, shap_df, market_env)
        return decision
