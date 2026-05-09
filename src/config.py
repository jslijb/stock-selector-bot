import os
import yaml
import time
import threading
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from loguru import logger


_CONFIG_INSTANCE = None
_LLM_MTIME = 0.0


@dataclass
class LLMConfig:
    provider: str = "dashscope"
    api_key_env: str = "DASHSCOPE_API_KEY"
    model: str = "qwen-plus"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key: str = ""
    max_tokens: int = 4096
    temperature: float = 0.3


@dataclass
class EmbeddingConfig:
    model_name: str = "BAAI/bge-large-zh-v1.5"
    device: str = "cpu"


@dataclass
class FactorsConfig:
    count: int = 150
    neutralization: str = "industry"
    extreme_value_method: str = "mad"
    zscore_window: int = 252


@dataclass
class ReasoningConfig:
    layer1_top_pct: float = 0.20
    layer2_top_n: int = 50
    layer3_final_n: int = 20


@dataclass
class RiskConfig:
    max_single_weight: float = 0.10
    industry_deviation: float = 0.05
    max_price: float = 150.0
    bj_min_market_cap: float = 30.0
    bj_min_price: float = 10.0
    exclude_st: bool = True
    loss_lookback_years: int = 5
    loss_min_years: int = 3
    excluded_industries: tuple = (
        "房地产", "房地产开发", "房地产服务",
        "纺织制造", "服装",
        "造纸", "包装印刷",
        "影视", "院线",
    )


@dataclass
class EvolutionConfig:
    frequency: str = "monthly"
    ic_window_months: int = 3
    weight_bounds: tuple = (0.01, 0.30)


@dataclass
class AppConfig:
    duckdb_path: str = "./data/stock_agent.duckdb"
    tushare_token_env: str = "TUSHARE_TOKEN"
    tushare_rate_limit: int = 200
    llm: LLMConfig = field(default_factory=LLMConfig)
    llm_sentiment: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    chromadb_persist_dir: str = "./data/chroma_db"
    chromadb_collection: str = "market_state_memory"
    factors: FactorsConfig = field(default_factory=FactorsConfig)
    reasoning: ReasoningConfig = field(default_factory=ReasoningConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    evolution: EvolutionConfig = field(default_factory=EvolutionConfig)
    check_missing: bool = True
    auto_backfill: bool = True


def _get_llm_config_path() -> Path:
    return Path(__file__).parent.parent / "config" / "llm_config.yaml"


def _load_llm_config_yaml() -> dict:
    path = _get_llm_config_path()
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _apply_llm_config(cfg: AppConfig, llm_raw: dict) -> None:
    api_key = llm_raw.get("api_key", "")
    api_key_env = "DASHSCOPE_API_KEY"
    if not api_key:
        api_key = os.environ.get(api_key_env, "")

    base_url = llm_raw.get("base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1")

    decision_model = llm_raw.get("decision_model", "qwen-plus")
    decision_max_tokens = llm_raw.get("decision_max_tokens", 4096)
    decision_temperature = llm_raw.get("decision_temperature", 0.3)

    sentiment_model = llm_raw.get("sentiment_model", "qwen-turbo")
    sentiment_max_tokens = llm_raw.get("sentiment_max_tokens", 1024)
    sentiment_temperature = llm_raw.get("sentiment_temperature", 0.1)

    cfg.llm = LLMConfig(
        provider="dashscope",
        api_key_env=api_key_env,
        model=decision_model,
        base_url=base_url,
        api_key=api_key,
        max_tokens=decision_max_tokens,
        temperature=decision_temperature,
    )
    cfg.llm_sentiment = LLMConfig(
        provider="dashscope",
        api_key_env=api_key_env,
        model=sentiment_model,
        base_url=base_url,
        api_key=api_key,
        max_tokens=sentiment_max_tokens,
        temperature=sentiment_temperature,
    )


def reload_llm_config(cfg: Optional[AppConfig] = None) -> AppConfig:
    global _CONFIG_INSTANCE
    if cfg is None:
        cfg = _CONFIG_INSTANCE
    if cfg is None:
        cfg = load_config()
    llm_raw = _load_llm_config_yaml()
    _apply_llm_config(cfg, llm_raw)
    _CONFIG_INSTANCE = cfg
    logger.info(f"LLM配置已热加载: decision={cfg.llm.model}, sentiment={cfg.llm_sentiment.model}")
    return cfg


_last_config_check = 0

def _check_llm_config_changed() -> bool:
    global _LLM_MTIME, _last_config_check
    now = time.time()
    if now - _last_config_check < 5:
        return False
    _last_config_check = now
    path = _get_llm_config_path()
    if not path.exists():
        return False
    mtime = path.stat().st_mtime
    if mtime > _LLM_MTIME:
        _LLM_MTIME = mtime
        return True
    return False


def _hot_reload_watcher(interval: float = 5.0):
    while True:
        time.sleep(interval)
        if _check_llm_config_changed():
            reload_llm_config()


def start_hot_reload():
    t = threading.Thread(target=_hot_reload_watcher, daemon=True)
    t.start()
    logger.info("配置热加载监控已启动 (每5秒检查)")


def load_config(config_path: Optional[str] = None) -> AppConfig:
    global _CONFIG_INSTANCE, _LLM_MTIME

    if config_path is None:
        config_path = Path(__file__).parent.parent / "config" / "settings.yaml"
    else:
        config_path = Path(config_path)

    cfg = AppConfig()

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        cfg.duckdb_path = raw.get("database", {}).get("duckdb_path", cfg.duckdb_path)
        cfg.tushare_token_env = raw.get("tushare", {}).get("token_env", cfg.tushare_token_env)
        cfg.tushare_rate_limit = raw.get("tushare", {}).get("rate_limit", cfg.tushare_rate_limit)

        emb_raw = raw.get("embedding", {})
        cfg.embedding = EmbeddingConfig(
            model_name=emb_raw.get("model_name", cfg.embedding.model_name),
            device=emb_raw.get("device", cfg.embedding.device),
        )

        chroma_raw = raw.get("chromadb", {})
        cfg.chromadb_persist_dir = chroma_raw.get("persist_dir", cfg.chromadb_persist_dir)
        cfg.chromadb_collection = chroma_raw.get("collection_name", cfg.chromadb_collection)

        fac_raw = raw.get("factors", {})
        cfg.factors = FactorsConfig(
            count=fac_raw.get("count", cfg.factors.count),
            neutralization=fac_raw.get("neutralization", cfg.factors.neutralization),
            extreme_value_method=fac_raw.get("extreme_value_method", cfg.factors.extreme_value_method),
            zscore_window=fac_raw.get("zscore_window", cfg.factors.zscore_window),
        )

        reas_raw = raw.get("reasoning", {})
        cfg.reasoning = ReasoningConfig(
            layer1_top_pct=reas_raw.get("layer1_top_pct", cfg.reasoning.layer1_top_pct),
            layer2_top_n=reas_raw.get("layer2_top_n", cfg.reasoning.layer2_top_n),
            layer3_final_n=reas_raw.get("layer3_final_n", cfg.reasoning.layer3_final_n),
        )

        risk_raw = raw.get("risk", {})
        cfg.risk = RiskConfig(
            max_single_weight=risk_raw.get("max_single_weight", cfg.risk.max_single_weight),
            industry_deviation=risk_raw.get("industry_deviation", cfg.risk.industry_deviation),
        )

        evo_raw = raw.get("evolution", {})
        cfg.evolution = EvolutionConfig(
            frequency=evo_raw.get("frequency", cfg.evolution.frequency),
            ic_window_months=evo_raw.get("ic_window_months", cfg.evolution.ic_window_months),
            weight_bounds=tuple(evo_raw.get("weight_bounds", list(cfg.evolution.weight_bounds))),
        )

        sched_raw = raw.get("scheduler", {})
        cfg.check_missing = sched_raw.get("check_missing", cfg.check_missing)
        cfg.auto_backfill = sched_raw.get("auto_backfill", cfg.auto_backfill)

    llm_raw = _load_llm_config_yaml()
    _apply_llm_config(cfg, llm_raw)

    llm_path = _get_llm_config_path()
    if llm_path.exists():
        _LLM_MTIME = llm_path.stat().st_mtime

    _CONFIG_INSTANCE = cfg
    return cfg


def get_config() -> AppConfig:
    global _CONFIG_INSTANCE
    if _CONFIG_INSTANCE is None:
        _CONFIG_INSTANCE = load_config()
    if _check_llm_config_changed():
        _CONFIG_INSTANCE = reload_llm_config(_CONFIG_INSTANCE)
    return _CONFIG_INSTANCE
