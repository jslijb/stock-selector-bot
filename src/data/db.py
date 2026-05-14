import duckdb
from pathlib import Path
from loguru import logger
from typing import Optional


class Database:
    _instance: Optional["Database"] = None

    def __init__(self, db_path: str = "./data/stock_agent.duckdb"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[duckdb.DuckDBPyConnection] = None

    @classmethod
    def get_instance(cls, db_path: str = "./data/stock_agent.duckdb") -> "Database":
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(str(self.db_path))
            logger.info(f"DuckDB connected: {self.db_path}")
        return self._conn

    def execute(self, sql: str, params=None):
        return self.conn.execute(sql, params) if params is None else self.conn.execute(sql, params)

    def locked_execute(self, table: str, date: str, sql: str, params=None):
        from .lock_manager import DateLockManager
        with DateLockManager.lock(table, date):
            return self.execute(sql, params)

    def fetch_df(self, sql: str, params=None):
        result = self.execute(sql, params)
        return result.df()

    def fetch_all(self, sql: str, params=None):
        result = self.execute(sql, params)
        return result.fetchall()

    def fetch_one(self, sql: str, params=None):
        result = self.execute(sql, params)
        return result.fetchone()

    def table_exists(self, table_name: str) -> bool:
        result = self.fetch_one(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
            [table_name],
        )
        return result[0] > 0

    def get_date_range(self, table_name: str, date_col: str = "trade_date") -> tuple:
        if not self.table_exists(table_name):
            return (None, None)
        result = self.fetch_one(f"SELECT MIN({date_col}), MAX({date_col}) FROM {table_name}")
        return (result[0], result[1])

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.info("DuckDB connection closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
