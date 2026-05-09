import os
import json
import pandas as pd
from loguru import logger
from datetime import datetime
from typing import List, Dict, Optional
from openai import OpenAI
from ..config import get_config
from ..data.db import Database

SENTIMENT_PROMPT = """你是一个专业的金融新闻分析助手。请对以下新闻进行分析，返回JSON格式结果。

新闻标题：{title}
新闻内容：{content}

请返回以下格式的JSON（不要包含其他内容）：
{{
  "sentiment": "positive/neutral/negative",
  "event_type": "事件类型（如：业绩公告/政策变动/行业动态/人事变动/诉讼风险/并购重组/其他）",
  "impact_score": 0.0-1.0的影响力评分,
  "affected_stocks": ["相关股票代码"]
}}
"""


class NLPSentimentModule:
    def __init__(self, db: Optional[Database] = None):
        self.cfg = get_config()
        self.db = db or Database.get_instance(self.cfg.duckdb_path)
        self._init_client()

    def _init_client(self):
        self.cfg = get_config()
        api_key = self.cfg.llm_sentiment.api_key or os.environ.get(self.cfg.llm_sentiment.api_key_env)
        if api_key:
            import httpx
            self.client = OpenAI(
                api_key=api_key, base_url=self.cfg.llm_sentiment.base_url,
                max_retries=2, timeout=httpx.Timeout(None, connect=15.0),
            )
        else:
            self.client = None
            logger.warning(f"未设置 {self.cfg.llm_sentiment.api_key_env}，LLM舆情模块将跳过")

    def analyze_news(self, title: str, content: str) -> Dict:
        self._init_client()
        if self.client is None:
            return {"sentiment": "neutral", "event_type": "其他", "impact_score": 0.0, "affected_stocks": []}

        prompt = SENTIMENT_PROMPT.format(title=title, content=content[:2000])

        try:
            import httpx
            timeout_obj = httpx.Timeout(None, connect=15.0)
            resp = self.client.chat.completions.create(
                model=self.cfg.llm_sentiment.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.cfg.llm_sentiment.max_tokens,
                temperature=0.1,
                timeout=timeout_obj,
            )
            text = resp.choices[0].message.content.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            return result
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失败: {e}, 原文: {text[:200]}")
            return {"sentiment": "neutral", "event_type": "其他", "impact_score": 0.0, "affected_stocks": []}
        except Exception as e:
            logger.error(f"LLM调用失败: {e}")
            return {"sentiment": "neutral", "event_type": "其他", "impact_score": 0.0, "affected_stocks": []}

    def batch_analyze(self, news_list: List[Dict]) -> List[Dict]:
        results = []
        for news in news_list:
            title = news.get("title", "")
            content = news.get("content", "")
            analysis = self.analyze_news(title, content)
            result = {**news, **analysis}
            results.append(result)
        return results

    def save_to_db(self, results: List[Dict], trade_date: str):
        if not results:
            return
        records = []
        for r in results:
            stocks = r.get("affected_stocks", [])
            ts_code = stocks[0] if stocks else None
            records.append({
                "ts_code": ts_code,
                "news_date": trade_date,
                "title": r.get("title", ""),
                "content": r.get("content", "")[:500],
                "sentiment": r.get("sentiment", "neutral"),
                "event_type": r.get("event_type", "其他"),
                "impact_score": r.get("impact_score", 0.0),
                "llm_model": self.cfg.llm_sentiment.model,
            })

        df = pd.DataFrame(records)
        df["news_date"] = pd.to_datetime(trade_date)
        temp = f"temp_news_{int(datetime.now().timestamp()*1000)}"
        self.db.conn.register(temp, df)
        try:
            self.db.execute(f"INSERT INTO news_tags (ts_code, news_date, title, content, sentiment, event_type, impact_score, llm_model) SELECT ts_code, news_date, title, content, sentiment, event_type, impact_score, llm_model FROM {temp}")
            logger.info(f"新闻标签已保存: {len(records)} 条")
        finally:
            try:
                self.db.conn.unregister(temp)
            except Exception:
                logger.opt(exception=True).debug("unregister临时表异常")

    def get_sentiment_factor(self, trade_date: str) -> pd.DataFrame:
        dt = trade_date if len(trade_date) != 8 else f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        sql = """
        SELECT ts_code,
               SUM(CASE WHEN sentiment='positive' THEN 1 WHEN sentiment='negative' THEN -1 ELSE 0 END) as news_sentiment_score,
               COUNT(*) as news_count,
               AVG(impact_score) as impact_score
        FROM news_tags
        WHERE news_date = ?
        AND ts_code IS NOT NULL
        GROUP BY ts_code
        """
        return self.db.fetch_df(sql, [dt])
