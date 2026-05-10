from loguru import logger


SCHEMA_SQL = {
    "daily_price": """
CREATE TABLE IF NOT EXISTS daily_price (
    ts_code     VARCHAR NOT NULL,
    trade_date  DATE NOT NULL,
    open        DOUBLE,
    high        DOUBLE,
    low         DOUBLE,
    close       DOUBLE,
    pre_close   DOUBLE,
    change      DOUBLE,
    pct_chg     DOUBLE,
    vol         DOUBLE,
    amount      DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
)
""",
    "adj_factor": """
CREATE TABLE IF NOT EXISTS adj_factor (
    ts_code     VARCHAR NOT NULL,
    trade_date  DATE NOT NULL,
    adj_factor  DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
)
""",
    "financials": """
CREATE TABLE IF NOT EXISTS financials (
    ts_code         VARCHAR NOT NULL,
    ann_date        DATE,
    report_period   VARCHAR NOT NULL,
    total_revenue   DOUBLE,
    revenue         DOUBLE,
    total_cogs      DOUBLE,
    oper_cost       DOUBLE,
    sell_exp        DOUBLE,
    admin_exp       DOUBLE,
    net_profit      DOUBLE,
    netprofit_cut   DOUBLE,
    total_assets    DOUBLE,
    total_liab      DOUBLE,
    total_hldr_eqy DOUBLE,
    op_yoys         DOUBLE,
    np_yoys         DOUBLE,
    roe             DOUBLE,
    roe_dt          DOUBLE,
    eps             DOUBLE,
    bps             DOUBLE,
    ocf_ps          DOUBLE,
    PRIMARY KEY (ts_code, report_period)
)
""",
    "money_flow": """
CREATE TABLE IF NOT EXISTS money_flow (
    ts_code     VARCHAR NOT NULL,
    trade_date  DATE NOT NULL,
    buy_sm_vol  DOUBLE,
    buy_sm_amount DOUBLE,
    sell_sm_vol DOUBLE,
    sell_sm_amount DOUBLE,
    buy_lg_vol  DOUBLE,
    buy_lg_amount DOUBLE,
    sell_lg_vol DOUBLE,
    sell_lg_amount DOUBLE,
    net_mf_vol  DOUBLE,
    net_mf_amount DOUBLE,
    north_net   DOUBLE,
    rz_ye       DOUBLE,
    rq_ye       DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
)
""",
    "news_tags": """
CREATE TABLE IF NOT EXISTS news_tags (
    id          INTEGER PRIMARY KEY DEFAULT nextval('news_tags_seq'),
    ts_code     VARCHAR,
    news_date   DATE NOT NULL,
    title       VARCHAR,
    content     VARCHAR,
    sentiment   VARCHAR,
    event_type  VARCHAR,
    impact_score DOUBLE,
    llm_model   VARCHAR,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""",
    "factors_daily": """
CREATE TABLE IF NOT EXISTS factors_daily (
    ts_code     VARCHAR NOT NULL,
    trade_date  DATE NOT NULL,
    factor_name VARCHAR NOT NULL,
    factor_value DOUBLE,
    PRIMARY KEY (ts_code, trade_date, factor_name)
)
""",
    "market_state_snapshot": """
CREATE TABLE IF NOT EXISTS market_state_snapshot (
    snapshot_date DATE NOT NULL PRIMARY KEY,
    market_return DOUBLE,
    volatility    DOUBLE,
    breadth       DOUBLE,
    sentiment_idx DOUBLE,
    description   VARCHAR,
    embedding_id  VARCHAR,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""",
    "decisions": """
CREATE TABLE IF NOT EXISTS decisions (
    id          INTEGER PRIMARY KEY DEFAULT nextval('decisions_seq'),
    trade_date  DATE NOT NULL,
    ts_code     VARCHAR NOT NULL,
    weight      DOUBLE,
    score       DOUBLE,
    ml_score    DOUBLE,
    reason      VARCHAR,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""",
    "decision_performance": """
CREATE TABLE IF NOT EXISTS decision_performance (
    id              INTEGER PRIMARY KEY DEFAULT nextval('decision_perf_seq'),
    trade_date      DATE NOT NULL,
    ts_code         VARCHAR NOT NULL,
    decision_weight DOUBLE,
    return_1d       DOUBLE,
    return_3d       DOUBLE,
    return_5d       DOUBLE,
    return_10d      DOUBLE,
    return_20d      DOUBLE,
    evaluated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""",
    "factor_weights_history": """
CREATE TABLE IF NOT EXISTS factor_weights_history (
    id          INTEGER PRIMARY KEY DEFAULT nextval('factor_weights_seq'),
    effective_date DATE NOT NULL,
    factor_name VARCHAR NOT NULL,
    weight      DOUBLE,
    ic_mean     DOUBLE,
    ic_std      DOUBLE,
    ir          DOUBLE,
    approved    BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""",
    "trade_calendar": """
CREATE TABLE IF NOT EXISTS trade_calendar (
    trade_date DATE NOT NULL PRIMARY KEY,
    is_open    BOOLEAN DEFAULT TRUE
)
""",
    "stock_basic": """
CREATE TABLE IF NOT EXISTS stock_basic (
    ts_code     VARCHAR NOT NULL PRIMARY KEY,
    symbol      VARCHAR,
    name        VARCHAR,
    area        VARCHAR,
    industry    VARCHAR,
    market      VARCHAR,
    list_date   DATE,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""",
    "daily_basic": """
CREATE TABLE IF NOT EXISTS daily_basic (
    ts_code         VARCHAR NOT NULL,
    trade_date      DATE NOT NULL,
    close           DOUBLE,
    pe_ttm          DOUBLE,
    pb              DOUBLE,
    ps_ttm          DOUBLE,
    pcf_ttm         DOUBLE,
    dv_ratio        DOUBLE,
    turnover_rate   DOUBLE,
    turnover_rate_f DOUBLE,
    volume_ratio    DOUBLE,
    total_mv        DOUBLE,
    circ_mv         DOUBLE,
    PRIMARY KEY (ts_code, trade_date)
)
""",
}

SEQUENCE_SQL = [
    "CREATE SEQUENCE IF NOT EXISTS news_tags_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS decisions_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS decision_perf_seq START 1",
    "CREATE SEQUENCE IF NOT EXISTS factor_weights_seq START 1",
]


def init_schema(db) -> None:
    logger.info("Initializing database schema...")
    for seq_sql in SEQUENCE_SQL:
        db.execute(seq_sql)

    for table_name, ddl in SCHEMA_SQL.items():
        if db.table_exists(table_name):
            logger.debug(f"Table {table_name} already exists, skipping")
            continue
        db.execute(ddl)
        logger.info(f"Created table: {table_name}")

    logger.info("Schema initialization complete")


TABLE_NAMES = list(SCHEMA_SQL.keys())
