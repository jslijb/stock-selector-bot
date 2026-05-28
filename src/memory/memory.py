import os
import json
import numpy as np
import pandas as pd
from loguru import logger
from datetime import datetime
from typing import List, Dict, Optional
from ..config import get_config
from ..data.db import Database

try:
    from modelscope import snapshot_download as ms_snapshot_download
    _MODELSCOPE_AVAILABLE = True
except ImportError:
    _MODELSCOPE_AVAILABLE = False

try:
    from chromadb import PersistentClient
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False

try:
    import chromadb
    _CHROMA_SDK = True
except ImportError:
    _CHROMA_SDK = False


def _create_chroma_client(persist_dir: str):
    if not _CHROMA_SDK:
        return None
    try:
        return PersistentClient(path=persist_dir)
    except Exception:
        try:
            settings = chromadb.Settings(
                chroma_db_impl="chromadb.db.sqlite.SqliteDB",
                persist_directory=persist_dir,
                anonymized_telemetry=False,
            )
            return chromadb.Client(settings)
        except Exception:
            try:
                return chromadb.EphemeralClient()
            except Exception as e:
                logger.warning(f"ChromaDB初始化失败: {e}")
                return None


class EpisodicMemory:
    def __init__(self, db: Optional[Database] = None):
        self.cfg = get_config()
        self.db = db or Database.get_instance(self.cfg.duckdb_path)

        self.client = _create_chroma_client(self.cfg.chromadb_persist_dir)
        self._use_chroma = self.client is not None

        if self._use_chroma:
            try:
                self.collection = self.client.get_or_create_collection(
                    name=self.cfg.chromadb_collection,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info(f"ChromaDB集合: {self.cfg.chromadb_collection}, 文档数: {self.collection.count()}")
            except Exception as e:
                logger.warning(f"ChromaDB集合初始化失败: {e}, 降级为DuckDB存储")
                self._use_chroma = False
                self.collection = None
        else:
            logger.warning("ChromaDB不可用，使用DuckDB降级存储(无向量检索)")

        model_name = self.cfg.embedding.model_name
        model_dir = self._download_model_from_modelscope(model_name, self.cfg.embedding.model_path)
        from sentence_transformers import SentenceTransformer
        self.encoder = SentenceTransformer(model_dir, device=self.cfg.embedding.device)
        logger.info(f"Embedding模型加载: {model_name} (from {model_dir})")

    @staticmethod
    def _download_model_from_modelscope(model_name: str, model_path: str = "") -> str:
        import os as _os

        if model_path and _os.path.isdir(model_path):
            logger.info(f"使用配置模型路径: {model_path}")
            return model_path

        local_candidates = [
            _os.path.join(_os.path.expanduser("~"), ".cache", "modelscope", "hub",
                           model_name.replace("/", _os.sep).replace(".", "_")),
            _os.path.join(_os.path.expanduser("~"), ".cache", "huggingface", "hub",
                           f"models--{model_name.replace('/', '--')}"),
        ]
        for candidate in local_candidates:
            if _os.path.isdir(candidate) and any(
                f.endswith(".bin") or f.endswith(".safetensors") or f.endswith(".pt")
                for f in _os.listdir(candidate)
            ):
                logger.info(f"使用本地模型: {candidate}")
                return candidate

        if _MODELSCOPE_AVAILABLE:
            logger.info(f"本地无模型，从魔塔社区下载: {model_name}")
            try:
                model_dir = ms_snapshot_download(model_name)
                logger.info(f"模型下载完成: {model_dir}")
                return model_dir
            except Exception as e:
                logger.warning(f"魔塔社区下载失败: {e}")

        logger.warning("使用模型名称直接加载(可能触发远程下载)")
        return model_name

    @staticmethod
    def _to_date(d: str) -> str:
        if len(d) == 8:
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        return d

    def encode(self, text: str) -> List[float]:
        vec = self.encoder.encode(text, show_progress_bar=False)
        return vec.tolist()

    def build_market_description(self, trade_date: str) -> str:
        dt = self._to_date(trade_date)
        row = self.db.fetch_one(
            "SELECT market_return, volatility, breadth, sentiment_idx, description FROM market_state_snapshot WHERE snapshot_date = ?",
            [dt],
        )
        if row is None:
            return f"日期{trade_date}无市场快照数据"
        ret, vol, breadth, sent, desc = row
        parts = [f"日期:{trade_date}"]
        if ret is not None:
            parts.append(f"市场收益率:{ret:.2%}")
        if vol is not None:
            parts.append(f"波动率:{vol:.4f}")
        if breadth is not None:
            parts.append(f"市场宽度:{breadth:.2%}")
        if sent is not None:
            parts.append(f"情绪指标:{sent:.2f}")
        if desc:
            parts.append(f"描述:{desc}")
        return "；".join(parts)

    def store_snapshot(self, trade_date: str, market_return: float, volatility: float,
                       breadth: float, sentiment_idx: float, description: str = ""):
        dt = self._to_date(trade_date)
        text = self.build_market_description(trade_date)
        if not description:
            description = text

        embedding = self.encode(text)

        doc_id = f"snapshot_{dt}"
        metadata = {
            "trade_date": dt,
            "market_return": float(market_return) if market_return else 0.0,
            "volatility": float(volatility) if volatility else 0.0,
            "breadth": float(breadth) if breadth else 0.0,
        }

        if self._use_chroma:
            try:
                self.collection.upsert(
                    ids=[doc_id],
                    embeddings=[embedding],
                    documents=[text],
                    metadatas=[metadata],
                )
            except Exception as e:
                logger.opt(exception=True).error(f"ChromaDB存储失败: {e}")

        self.db.execute(
            """INSERT OR REPLACE INTO market_state_snapshot
            (snapshot_date, market_return, volatility, breadth, sentiment_idx, description, embedding_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [dt, market_return, volatility, breadth, sentiment_idx, description, doc_id],
        )

        self._store_embedding(doc_id, embedding, text, metadata)
        logger.info(f"市场快照已存储: {trade_date}")

    def _store_embedding(self, doc_id: str, embedding: List[float], text: str, metadata: Dict):
        try:
            self.db.execute(
                """CREATE TABLE IF NOT EXISTS embedding_store (
                    doc_id VARCHAR PRIMARY KEY,
                    embedding VARCHAR,
                    text VARCHAR,
                    metadata VARCHAR
                )"""
            )
            self.db.execute(
                "INSERT OR REPLACE INTO embedding_store (doc_id, embedding, text, metadata) VALUES (?, ?, ?, ?)",
                [doc_id, json.dumps(embedding), text, json.dumps(metadata)],
            )
        except Exception as e:
            logger.opt(exception=True).debug(f"embedding存储失败: {e}")

    def retrieve_similar(self, trade_date: str, top_k: int = 3) -> List[Dict]:
        if self._use_chroma:
            return self._retrieve_chroma(trade_date, top_k)
        return self._retrieve_fallback(trade_date, top_k)

    def _retrieve_chroma(self, trade_date: str, top_k: int = 3) -> List[Dict]:
        dt = self._to_date(trade_date)
        query_text = self.build_market_description(trade_date)
        query_embedding = self.encode(query_text)

        try:
            count = self.collection.count()
        except Exception:
            logger.opt(exception=True).debug("ChromaDB计数异常")
            count = 0

        if count == 0:
            return []

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k + 1, count),
            include=["documents", "metadatas", "distances"],
        )

        similar_days = []
        if not results["ids"]:
            return similar_days

        for i, doc_id in enumerate(results["ids"][0]):
            meta = results["metadatas"][0][i]
            dist = results["distances"][0][i]
            doc = results["documents"][0][i]
            if meta.get("trade_date") == dt:
                continue
            similar_days.append({
                "trade_date": meta.get("trade_date"),
                "description": doc,
                "distance": dist,
                "similarity": 1 - dist,
                "market_return": meta.get("market_return"),
                "volatility": meta.get("volatility"),
                "breadth": meta.get("breadth"),
            })
            if len(similar_days) >= top_k:
                break

        return similar_days

    def _retrieve_fallback(self, trade_date: str, top_k: int = 3) -> List[Dict]:
        try:
            rows = self.db.fetch_all("SELECT doc_id, embedding, text, metadata FROM embedding_store")
        except Exception:
            return []

        if not rows:
            return []

        query_text = self.build_market_description(trade_date)
        query_vec = np.array(self.encode(query_text))

        scored = []
        for doc_id, emb_str, text, meta_str in rows:
            try:
                emb = np.array(json.loads(emb_str))
                meta = json.loads(meta_str)
                if meta.get("trade_date") == self._to_date(trade_date):
                    continue
                cos = np.dot(query_vec, emb) / (np.linalg.norm(query_vec) * np.linalg.norm(emb) + 1e-8)
                scored.append((meta, text, cos))
            except Exception:
                continue

        scored.sort(key=lambda x: x[2], reverse=True)

        similar_days = []
        for meta, doc, cos in scored[:top_k]:
            dist = 1 - cos
            similar_days.append({
                "trade_date": meta.get("trade_date"),
                "description": doc,
                "distance": dist,
                "similarity": cos,
                "market_return": meta.get("market_return"),
                "volatility": meta.get("volatility"),
                "breadth": meta.get("breadth"),
            })
        return similar_days

    def get_historical_decision(self, trade_date: str) -> Optional[Dict]:
        dt = self._to_date(trade_date)
        decisions = self.db.fetch_df(
            """SELECT ts_code, weight, score, reason FROM decisions WHERE trade_date = ?""",
            [dt],
        )
        if decisions.empty:
            return None
        return {
            "trade_date": trade_date,
            "holdings": decisions[["ts_code", "weight", "score", "reason"]].to_dict("records"),
        }

    def get_performance_after(self, trade_date: str) -> Optional[Dict]:
        dt = self._to_date(trade_date)
        perf = self.db.fetch_df(
            """SELECT ts_code, decision_weight, return_1d, return_3d, return_5d, return_10d, return_20d
            FROM decision_performance WHERE trade_date = ?""",
            [dt],
        )
        if perf.empty:
            return None
        return {
            "trade_date": trade_date,
            "performance": perf.to_dict("records"),
        }
