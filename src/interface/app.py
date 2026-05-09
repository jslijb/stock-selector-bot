import streamlit as st
import pandas as pd
from datetime import datetime


st.set_page_config(page_title="认知型智能选股 Agent", layout="wide")
st.title("认知型智能选股 Agent")

from src.data.db import Database
from src.config import get_config
from src.data.schema import init_schema

cfg = get_config()
db = Database.get_instance(cfg.duckdb_path)
init_schema(db)


def _date_fmt(d):
    if hasattr(d, "strftime"):
        return d.strftime("%Y%m%d")
    s = str(d)[:10].replace("-", "")
    return s


with st.sidebar:
    st.header("控制面板")
    trade_date = st.text_input("交易日期", value=datetime.now().strftime("%Y%m%d"))
    run_btn = st.button("执行选股", type="primary")
    evolve_btn = st.button("月度进化")
    approve_btn = st.button("批准权重")
    check_btn = st.button("检查缺失")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["选股结果", "最新持仓", "因子概览", "历史决策", "进化状态"])


with tab1:
    if run_btn:
        with st.spinner("运行选股流程..."):
            from src.scheduler import Scheduler
            scheduler = Scheduler()
            holdings = scheduler.run_daily(trade_date)
            if holdings:
                df = pd.DataFrame(holdings)
                df = df.sort_values("weight", ascending=False)
                st.subheader(f"选股结果 ({trade_date})")
                st.dataframe(df, use_container_width=True)
                st.bar_chart(df.set_index("ts_code")["weight"])
                codes = df["ts_code"].tolist()
                st.success(f"持仓代码: {', '.join(codes)}")
            else:
                st.warning("无选股结果")

with tab2:
    st.subheader("最新持仓 (从DB读取)")
    try:
        latest = db.fetch_df(
            "SELECT MAX(trade_date) as d FROM decisions"
        )
        if not latest.empty and latest.iloc[0]["d"] is not None:
            latest_date = latest.iloc[0]["d"]
            latest_str = _date_fmt(latest_date)
            decisions = db.fetch_df(
                "SELECT ts_code, weight, score, reason FROM decisions WHERE trade_date = ? ORDER BY weight DESC",
                [latest_date],
            )
            if not decisions.empty:
                st.metric("最新决策日期", latest_str)
                st.dataframe(decisions, use_container_width=True)
                st.bar_chart(decisions.set_index("ts_code")["weight"])
                codes = decisions["ts_code"].tolist()
                st.success(f"持仓代码: {', '.join(codes)}")
            else:
                st.info("无决策数据")
        else:
            st.info("无决策数据")
    except Exception as e:
        st.error(f"查询失败: {e}")

with tab3:
    if st.button("查看因子"):
        from src.factors.engine import FactorEngine
        from src.factors.registry import FactorRegistry
        engine = FactorEngine(db)
        factors_data = [{"名称": k, "类别": v.category, "描述": v.description}
                        for k, v in FactorRegistry.all_factors().items()]
        st.dataframe(pd.DataFrame(factors_data), use_container_width=True)
        st.metric("总因子数", FactorRegistry.count())

with tab4:
    if st.button("查询历史"):
        try:
            df = db.fetch_df(
                "SELECT trade_date, ts_code, weight, score, reason FROM decisions ORDER BY trade_date DESC LIMIT 100"
            )
            if not df.empty:
                df["trade_date"] = df["trade_date"].apply(_date_fmt)
                st.dataframe(df, use_container_width=True)
            else:
                st.info("无历史决策")
        except Exception as e:
            st.error(f"查询失败: {e}")

with tab5:
    if evolve_btn:
        with st.spinner("进化中..."):
            from src.evolution.evolver import FactorEvolver
            evolver = FactorEvolver(db)
            weights = evolver.run_monthly_evolution(trade_date)
            if weights:
                st.json(weights)
            else:
                st.warning("进化未产生新权重")

    if approve_btn:
        from src.evolution.evolver import FactorEvolver
        evolver = FactorEvolver(db)
        dt = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        evolver.approve_weights(dt)
        st.success(f"已批准: {trade_date}")

    if check_btn:
        from src.scheduler import Scheduler
        scheduler = Scheduler()
        result = scheduler.get_missing_dates("20240101", trade_date)
        st.metric("交易日", result["total_trade_days"])
        st.warning(f"缺失行情: {len(result['missing_data'])} 天")
        if result["missing_data"]:
            st.text(result["missing_data"][:20])
        st.warning(f"缺失因子: {len(result['missing_factor'])} 天")
        st.warning(f"缺失决策: {len(result['missing_decision'])} 天")
