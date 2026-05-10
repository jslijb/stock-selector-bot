import time
import pandas as pd
import numpy as np
from loguru import logger
from datetime import datetime, timedelta
from typing import Optional, Dict
from .config import get_config
from .data.db import Database
from .data.schema import init_schema
from .data.collector import TushareCollector
from .factors.engine import FactorEngine
from .factors.nlp_sentiment import NLPSentimentModule
from .memory.memory import EpisodicMemory
from .reasoning.engine import ReasoningEngine
from .risk.manager import RiskManager
from .evolution.evolver import FactorEvolver


class Scheduler:
    def __init__(self):
        self.cfg = get_config()
        self.db = Database.get_instance(self.cfg.duckdb_path)
        init_schema(self.db)

        self.collector = TushareCollector(self.db)
        self.factor_engine = FactorEngine(self.db)
        self._industry_map: Dict[str, str] = {}
        self.nlp = NLPSentimentModule(self.db)
        self.memory = EpisodicMemory(self.db)
        self.reasoning = ReasoningEngine(self.db, self.factor_engine, self.memory)
        self.risk = RiskManager(self.db)
        self.evolver = FactorEvolver(self.db)
        self._trade_day_cache: set = set()
        self._is_backfill: bool = False

    def _get_industry(self, stock_codes) -> pd.Series:
        if not self._industry_map:
            self._industry_map = self.collector.get_industry_map()
        industry = pd.Series("unknown", index=stock_codes)
        for code in stock_codes:
            if code in self._industry_map:
                industry[code] = self._industry_map[code]
        return industry

    def _pre_screen(self, factor_pivot: pd.DataFrame, trade_date: str) -> pd.DataFrame:
        dt = self._to_date(trade_date)
        before = len(factor_pivot)
        mask = pd.Series(True, index=factor_pivot.index)

        bj_codes = factor_pivot.index.str.endswith(".BJ")
        if bj_codes.any():
            if not self.cfg.risk.enable_bj:
                mask &= ~bj_codes
                logger.debug(f"过滤北交所: {bj_codes.sum()} 只")
            else:
                self._ensure_board_data("BJ", trade_date)
                try:
                    if self.db.table_exists("daily_basic"):
                        bj_list = factor_pivot.index[bj_codes].tolist()
                        placeholders = ",".join(["?"] * len(bj_list))
                        mv_df = self.db.fetch_df(
                            f"""SELECT ts_code, total_mv FROM daily_basic
                            WHERE trade_date = ? AND ts_code IN ({placeholders})""",
                            [dt] + bj_list,
                        )
                        if not mv_df.empty:
                            bj_mv_thresh = self.cfg.risk.bj_min_market_cap * 10000.0
                            small_bj = set(mv_df[mv_df["total_mv"] < bj_mv_thresh]["ts_code"])
                            mask &= ~factor_pivot.index.isin(small_bj)
                except Exception as e:
                    raise RuntimeError(f"北交所市值过滤失败，数据质量不可靠: {e}") from e

        kcb_codes = factor_pivot.index.str.startswith("688")
        if kcb_codes.any():
            if not self.cfg.risk.enable_kcb:
                mask &= ~kcb_codes
                logger.debug(f"过滤科创板: {kcb_codes.sum()} 只")
            else:
                self._ensure_board_data("KCB", trade_date)
                try:
                    if self.db.table_exists("daily_basic"):
                        kcb_list = factor_pivot.index[kcb_codes].tolist()
                        placeholders = ",".join(["?"] * len(kcb_list))
                        mv_df = self.db.fetch_df(
                            f"""SELECT ts_code, total_mv FROM daily_basic
                            WHERE trade_date = ? AND ts_code IN ({placeholders})""",
                            [dt] + kcb_list,
                        )
                        if not mv_df.empty:
                            kcb_mv_thresh = self.cfg.risk.kcb_min_market_cap * 10000.0
                            small_kcb = set(mv_df[mv_df["total_mv"] < kcb_mv_thresh]["ts_code"])
                            mask &= ~factor_pivot.index.isin(small_kcb)
                except Exception as e:
                    raise RuntimeError(f"科创板市值过滤失败，数据质量不可靠: {e}") from e

        if self.cfg.risk.exclude_st:
            try:
                names = self.db.fetch_df("SELECT ts_code, name FROM stock_basic WHERE name IS NOT NULL")
                if not names.empty:
                    st_codes = set(names[names["name"].str.contains("ST", case=False, na=False)]["ts_code"])
                    mask &= ~factor_pivot.index.isin(st_codes)
            except Exception as e:
                raise RuntimeError(f"ST过滤失败，退市风险股无法排除: {e}") from e

        try:
            price_df = self.db.fetch_df(
                "SELECT ts_code, close FROM daily_price WHERE trade_date = ?", [dt]
            )
            if not price_df.empty:
                high_codes = set(price_df[price_df["close"] > self.cfg.risk.max_price]["ts_code"])
                mask &= ~factor_pivot.index.isin(high_codes)
        except Exception as e:
            raise RuntimeError(f"高价股过滤失败: {e}") from e

        try:
            if self.db.table_exists("daily_basic"):
                mv_df = self.db.fetch_df(
                    "SELECT ts_code, total_mv FROM daily_basic WHERE trade_date = ?", [dt]
                )
                if not mv_df.empty:
                    mv_threshold = self.cfg.risk.min_market_cap * 10000.0
                    small_mv = set(mv_df[mv_df["total_mv"] < mv_threshold]["ts_code"])
                    mask &= ~factor_pivot.index.isin(small_mv)
        except Exception as e:
            raise RuntimeError(f"市值过滤失败: {e}") from e

        try:
            if self.db.table_exists("daily_basic"):
                turn_df = self.db.fetch_df(
                    "SELECT ts_code, turnover_rate FROM daily_basic WHERE trade_date = ?", [dt]
                )
                if not turn_df.empty:
                    low_turn = set(turn_df[turn_df["turnover_rate"] < self.cfg.risk.min_turnover_rate]["ts_code"])
                    mask &= ~factor_pivot.index.isin(low_turn)
        except Exception as e:
            raise RuntimeError(f"换手率过滤失败: {e}") from e

        try:
            amount_df = self.db.fetch_df(
                "SELECT ts_code, amount FROM daily_price WHERE trade_date = ?", [dt]
            )
            if not amount_df.empty:
                low_amount = set(amount_df[amount_df["amount"] < self.cfg.risk.min_avg_amount * 10.0]["ts_code"])
                mask &= ~factor_pivot.index.isin(low_amount)
        except Exception as e:
            raise RuntimeError(f"成交额过滤失败: {e}") from e

        if not self._industry_map:
            self._industry_map = self.collector.get_industry_map()

        cyclical_set = set(self.cfg.risk.cyclical_industries)

        try:
            fin_df = self.db.fetch_df(
                "SELECT ts_code, total_revenue, net_profit, total_hldr_eqy, total_liab, total_assets FROM financials"
            )
        except Exception as e:
            raise RuntimeError(f"财务数据查询失败，无法执行基本面过滤: {e}") from e

        if not fin_df.empty:
            latest_fin = fin_df.sort_values("ts_code").groupby("ts_code").last()

            revenue_thresh = self.cfg.risk.min_revenue * 1e8
            low_revenue = set(latest_fin[latest_fin["total_revenue"] < revenue_thresh].index)
            mask &= ~factor_pivot.index.isin(low_revenue)

            neg_equity = set(latest_fin[latest_fin["total_hldr_eqy"] <= 0].index)
            mask &= ~factor_pivot.index.isin(neg_equity)

            screened_codes = factor_pivot.index[mask]
            non_cyclical_loss = set()
            cyclical_fail = set()
            for code in screened_codes:
                if code not in latest_fin.index:
                    continue
                row = latest_fin.loc[code]
                industry = self._industry_map.get(code, "")
                is_cyclical = industry and any(c in industry for c in cyclical_set)

                if not is_cyclical:
                    if row.get("net_profit", 0) <= 0:
                        non_cyclical_loss.add(code)
                else:
                    try:
                        debt_ratio = row.get("total_liab", 0) / row.get("total_assets", 1) * 100
                        if debt_ratio > self.cfg.risk.cyclical_max_debt_ratio:
                            cyclical_fail.add(code)
                    except Exception:
                        pass

            mask &= ~factor_pivot.index.isin(non_cyclical_loss)
            mask &= ~factor_pivot.index.isin(cyclical_fail)

        excluded_ind = set(self.cfg.risk.excluded_industries)
        if excluded_ind:
            ind_codes = set()
            for code in factor_pivot.index[mask]:
                ind = self._industry_map.get(code, "")
                if ind and any(ex in ind for ex in excluded_ind):
                    ind_codes.add(code)
            mask &= ~factor_pivot.index.isin(ind_codes)

        try:
            if self.db.table_exists("daily_basic"):
                pe_df = self.db.fetch_df(
                    "SELECT ts_code, pe_ttm FROM daily_basic WHERE trade_date = ?", [dt]
                )
                if not pe_df.empty:
                    pe_map = dict(zip(pe_df["ts_code"], pe_df["pe_ttm"]))
                    screened_codes = factor_pivot.index[mask]
                    bad_pe_codes = set()
                    for code in screened_codes:
                        industry = self._industry_map.get(code, "")
                        is_cyc = industry and any(c in industry for c in cyclical_set)
                        if is_cyc:
                            continue
                        pe_val = pe_map.get(code)
                        if pe_val is None or np.isnan(pe_val) or pe_val <= 0 or pe_val > self.cfg.risk.max_pe_noncyclical:
                            bad_pe_codes.add(code)
                    mask &= ~factor_pivot.index.isin(bad_pe_codes)
        except Exception as e:
            raise RuntimeError(f"PE过滤失败: {e}") from e

        result = factor_pivot.loc[mask]
        removed = before - len(result)
        if removed > 0:
            logger.info(f"粗筛剔除: {removed} 只, 剩余 {len(result)} 只")
        return result

    def _ensure_board_data(self, board: str, trade_date: str):
        if board == "BJ":
            suffix = ".BJ"
            board_name = "北交所"
        elif board == "KCB":
            suffix = ".SH"
            prefix = "688"
            board_name = "科创板"
        else:
            return

        try:
            if board == "BJ":
                cnt = self.db.fetch_one(
                    "SELECT COUNT(*) FROM stock_basic WHERE ts_code LIKE '%.BJ'"
                )
            else:
                cnt = self.db.fetch_one(
                    "SELECT COUNT(*) FROM stock_basic WHERE ts_code LIKE '688%.SH'"
                )
            if cnt and cnt[0] > 0:
                return
            logger.info(f"{board_name}stock_basic无数据，开始从网络同步...")
            self._sync_board_stock_basic(board)
        except Exception as e:
            raise RuntimeError(f"{board_name}数据同步检查失败: {e}") from e

    def _sync_board_stock_basic(self, board: str):
        try:
            import akshare as ak
            if board == "BJ":
                df = ak.stock_bj_a_spot_em()
                if df.empty:
                    logger.warning("akshare未返回北交所数据")
                    return
                code_col = "代码" if "代码" in df.columns else df.columns[0]
                name_col = "名称" if "名称" in df.columns else df.columns[1]
                rows = []
                for _, r in df.iterrows():
                    code = str(r[code_col]).zfill(6)
                    rows.append({
                        "ts_code": f"{code}.BJ",
                        "symbol": code,
                        "name": r[name_col],
                        "market": "BJ",
                    })
            else:
                df = ak.stock_kc_a_spot_em()
                if df.empty:
                    logger.warning("akshare未返回科创板数据")
                    return
                code_col = "代码" if "代码" in df.columns else df.columns[0]
                name_col = "名称" if "名称" in df.columns else df.columns[1]
                rows = []
                for _, r in df.iterrows():
                    code = str(r[code_col]).zfill(6)
                    rows.append({
                        "ts_code": f"{code}.SH",
                        "symbol": code,
                        "name": r[name_col],
                        "market": "科创板",
                    })

            if not rows:
                return
            import pandas as pd_inner
            basic_df = pd_inner.DataFrame(rows)
            temp = f"temp_board_basic_{int(time.time()*1000)}"
            self.db.conn.register(temp, basic_df)
            cols = ", ".join(basic_df.columns)
            self.db.execute(f"INSERT OR IGNORE INTO stock_basic ({cols}) SELECT {cols} FROM {temp}")
            self.db.conn.unregister(temp)
            logger.info(f"{board}stock_basic同步完成: {len(rows)} 只")
        except Exception as e:
            raise RuntimeError(f"{board}数据同步失败: {e}") from e

    def _to_date(self, trade_date: str) -> str:
        if len(trade_date) == 8:
            return f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        return trade_date

    def _merge_daily_basic(self, price_df: pd.DataFrame, end_date: str) -> pd.DataFrame:
        dt = self._to_date(end_date)
        try:
            if not self.db.table_exists("daily_basic"):
                return price_df
            basic_cols = "ts_code,trade_date,pe_ttm,pb,ps_ttm,pcf_ttm,dv_ratio,turnover_rate,total_mv,circ_mv"
            basic_df = self.db.fetch_df(
                f"""SELECT {basic_cols} FROM daily_basic
                WHERE trade_date <= ? AND trade_date >= CAST(? AS DATE) - INTERVAL 252 DAY
                ORDER BY ts_code, trade_date""",
                [dt, dt],
            )
            if basic_df.empty:
                logger.debug("daily_basic无数据，跳过合并")
                return price_df
            new_cols = [c for c in basic_df.columns if c not in price_df.columns]
            if not new_cols:
                return price_df
            basic_merge = basic_df.set_index(["ts_code", "trade_date"])[new_cols]
            price_indexed = price_df.set_index(["ts_code", "trade_date"])
            common_idx = price_indexed.index.intersection(basic_merge.index)
            if len(common_idx) == 0:
                return price_df
            for col in new_cols:
                price_indexed.loc[common_idx, col] = basic_merge.loc[common_idx, col].values
            result = price_indexed.reset_index()
            logger.debug(f"合并daily_basic: {len(common_idx)}行, 新增列{new_cols}")
            return result
        except Exception as e:
            raise RuntimeError(f"合并daily_basic失败，估值因子将全为NaN: {e}") from e

    def _is_trade_day(self, date_str: str) -> bool:
        if date_str in self._trade_day_cache:
            return True
        try:
            cnt = self.db.fetch_one(
                "SELECT COUNT(*) FROM daily_price WHERE trade_date = ?",
                [self._to_date(date_str)],
            )
            if cnt and cnt[0] > 0:
                self._trade_day_cache.add(date_str)
                return True
        except Exception as e:
            raise RuntimeError(f"交易日历查询失败: {e}") from e
        try:
            cal = self.collector.get_trade_calendar(date_str, date_str)
            is_td = len(cal) > 0
            if is_td:
                self._trade_day_cache.add(date_str)
            return is_td
        except Exception as e:
            raise RuntimeError(f"交易日历获取失败: {e}") from e

    def _has_factor_data(self, dt: str) -> bool:
        dt = self._to_date(dt)
        try:
            cnt = self.db.fetch_one(
                "SELECT COUNT(*) FROM factors_daily WHERE trade_date = ?", [dt]
            )
            return cnt is not None and cnt[0] > 0
        except Exception as e:
            raise RuntimeError(f"因子数据查询失败: {e}") from e

    def _has_decision_data(self, dt: str) -> bool:
        dt = self._to_date(dt)
        try:
            cnt = self.db.fetch_one(
                "SELECT COUNT(*) FROM decisions WHERE trade_date = ?", [dt]
            )
            return cnt is not None and cnt[0] > 0
        except Exception as e:
            raise RuntimeError(f"决策数据查询失败: {e}") from e

    def run_daily(self, trade_date: Optional[str] = None):
        if trade_date is None:
            trade_date = datetime.now().strftime("%Y%m%d")

        logger.info(f"{'='*50}")
        logger.info(f"每日选股流程启动: {trade_date}")
        logger.info(f"{'='*50}")

        if not self._is_trade_day(trade_date):
            logger.info(f"非交易日 {trade_date}，跳过")
            return

        dt = self._to_date(trade_date)

        logger.info("[1/7] 数据采集")
        self.collector.run_daily(trade_date)

        logger.info("[2/7] 因子计算")
        if self._has_factor_data(dt):
            logger.debug(f"因子数据已存在，跳过计算: {trade_date}")
        else:
            price_df = self.db.fetch_df(
                "SELECT * FROM daily_price WHERE trade_date = ?",
                [dt],
            )
            if price_df.empty:
                logger.error(f"无行情数据: {trade_date}")
                return

            if self.cfg.check_missing:
                hist_sql = f"""SELECT * FROM daily_price WHERE trade_date IN (
                    SELECT DISTINCT trade_date FROM daily_price
                    WHERE trade_date <= '{dt}' ORDER BY trade_date DESC LIMIT 253
                ) ORDER BY ts_code, trade_date"""
                full_price = self.db.fetch_df(hist_sql)
                if full_price.empty:
                    logger.error(f"无历史数据: {trade_date}")
                    return
                full_price = self._merge_daily_basic(full_price, dt)
                stock_codes = full_price["ts_code"].unique()
                industry = self._get_industry(stock_codes)
                factor_df = self.factor_engine.pipeline(full_price, industry)
                self.factor_engine.save_factors(factor_df, trade_date)

        logger.info("[3/7] 舆情分析 (如有新闻)")
        sentiment_df = self.nlp.get_sentiment_factor(dt)

        logger.info("[4/7] 情景记忆存储")
        if not self._is_backfill:
            self._store_market_snapshot(trade_date)

        if self._has_decision_data(dt):
            logger.info(f"决策数据已存在，跳过推理/风控/进化: {trade_date}")
            return

        logger.info("[5/7] 三层推理")
        factor_wide = self.db.fetch_df(
            """SELECT ts_code, factor_name, factor_value FROM factors_daily WHERE trade_date = ?""",
            [dt],
        )
        if factor_wide.empty:
            logger.error("无因子数据，跳过推理")
            return

        factor_pivot = factor_wide.pivot(index="ts_code", columns="factor_name", values="factor_value")
        factor_pivot = self._pre_screen(factor_pivot, trade_date)
        if factor_pivot.empty:
            logger.error("初筛后无股票，跳过推理")
            return
        market_env = self._get_market_env(trade_date)
        decision = self.reasoning.run_full_pipeline(trade_date, factor_pivot, market_env)

        logger.info("[6/7] 风控校验")
        result = self.risk.validate_and_adjust(decision.get("holdings", []))
        final_holdings = result["holdings"]

        if not result["is_valid"]:
            logger.warning(f"风控违规: {result['violations']}")

        self.risk.save_decision(trade_date, final_holdings)

        logger.info("[7/7] 绩效评估 + 自动进化")
        self.evolver.evaluate_performance(trade_date)
        if not self._is_backfill:
            self._auto_evolve(trade_date)

        logger.info(f"每日选股完成: {trade_date}, 持仓 {len(final_holdings)} 只")
        return final_holdings

    def _auto_evolve(self, trade_date: str):
        try:
            last_evo = self.db.fetch_one(
                "SELECT MAX(effective_date) FROM factor_weights_history"
            )
            if last_evo and last_evo[0]:
                last_dt = last_evo[0]
                if isinstance(last_dt, str):
                    last_dt = datetime.strptime(last_dt, "%Y-%m-%d").date()
                elif isinstance(last_dt, datetime):
                    last_dt = last_dt.date()
                days_since = (datetime.strptime(trade_date, "%Y%m%d").date() - last_dt).days
                if days_since < 30:
                    return

            weights = self.evolver.run_monthly_evolution(trade_date)
            if weights:
                self.evolver.approve_weights(self._to_date(trade_date))
                logger.info(f"因子权重已自动进化并生效: {len(weights)} 个因子")
        except Exception as e:
            logger.opt(exception=True).debug(f"自动进化跳过: {e}")

    def run_backfill(self, start_date: str, end_date: str):
        logger.info(f"补跑模式: {start_date} ~ {end_date}")
        self._is_backfill = True
        trade_dates = self.collector.get_trade_calendar(start_date, end_date)
        self._trade_day_cache.update(trade_dates)
        logger.info(f"交易日 {len(trade_dates)} 天，已缓存")
        for td in trade_dates:
            try:
                self.run_daily(td)
            except Exception as e:
                import traceback
                logger.error(f"补跑 {td} 失败: {e}\n{traceback.format_exc()}")
        self._is_backfill = False
        logger.info("补跑完成，执行最终进化")
        if trade_dates:
            try:
                self._auto_evolve(trade_dates[-1])
            except Exception as e:
                logger.warning(f"最终进化失败: {e}")

    def run_backfill_phase1(self, start_date: str, end_date: str):
        logger.info(f"=== 第一阶段: 数据采集 ({start_date} ~ {end_date}) ===")
        self._is_backfill = True
        trade_dates = self.collector.get_trade_calendar(start_date, end_date)
        self._trade_day_cache.update(trade_dates)
        logger.info(f"交易日 {len(trade_dates)} 天")
        for i, td in enumerate(trade_dates, 1):
            try:
                logger.info(f"[{i}/{len(trade_dates)}] 采集: {td}")
                self.collector.run_daily(td, skip_money_flow=True)
            except Exception as e:
                import traceback
                logger.error(f"阶段1 {td} 失败: {e}\n{traceback.format_exc()}")
        self._is_backfill = False
        failed = self.collector.get_failed_dates()
        if failed:
            logger.warning(f"采集失败 {len(failed)} 天: {failed}")
        logger.info("第一阶段完成: 数据就绪")

    def run_backfill_moneyflow(self, start_date: str, end_date: str):
        logger.info(f"=== 补跑资金流向 ({start_date} ~ {end_date}) ===")
        trade_dates = self.collector.get_trade_calendar(start_date, end_date)
        self._trade_day_cache.update(trade_dates)
        logger.info(f"交易日 {len(trade_dates)} 天")
        for i, td in enumerate(trade_dates, 1):
            try:
                dt = self._to_date(td)
                cnt = self.db.fetch_one(
                    "SELECT COUNT(*) FROM money_flow WHERE trade_date = ?", [dt]
                )
                if cnt and cnt[0] > 0:
                    logger.debug(f"资金流向已存在，跳过: {td}")
                    continue
                logger.info(f"[{i}/{len(trade_dates)}] 资金流向: {td}")
                self.collector.fetch_money_flow(td)
            except Exception as e:
                import traceback
                logger.error(f"资金流向 {td} 失败: {e}\n{traceback.format_exc()}")
        logger.info("资金流向补跑完成")

    def run_backfill_phase2(self, start_date: str, end_date: str, force: bool = False):
        logger.info(f"=== 第二阶段: 因子计算 + 选股 ({start_date} ~ {end_date}) ===")
        self._is_backfill = True
        trade_dates = self.collector.get_trade_calendar(start_date, end_date)
        self._trade_day_cache.update(trade_dates)
        logger.info(f"交易日 {len(trade_dates)} 天")
        for i, td in enumerate(trade_dates, 1):
            try:
                dt = self._to_date(td)
                price_cnt = self.db.fetch_one(
                    "SELECT COUNT(*) FROM daily_price WHERE trade_date = ?", [dt]
                )
                if price_cnt is None or price_cnt[0] == 0:
                    logger.info(f"[{i}/{len(trade_dates)}] {td} 非交易日(无行情)，跳过")
                    continue
                if force or not self._has_factor_data(dt):
                    price_df = self.db.fetch_df(
                        "SELECT * FROM daily_price WHERE trade_date = ?", [dt],
                    )
                    if not price_df.empty and self.cfg.check_missing:
                        hist_sql = f"""SELECT * FROM daily_price WHERE trade_date IN (
                            SELECT DISTINCT trade_date FROM daily_price
                            WHERE trade_date <= '{dt}' ORDER BY trade_date DESC LIMIT 253
                        ) ORDER BY ts_code, trade_date"""
                        full_price = self.db.fetch_df(hist_sql)
                        if not full_price.empty:
                            full_price = self._merge_daily_basic(full_price, dt)
                            if force:
                                self.db.execute(f"DELETE FROM factors_daily WHERE trade_date = '{dt}'")
                            stock_codes = full_price["ts_code"].unique()
                            industry = self._get_industry(stock_codes)
                            factor_df = self.factor_engine.pipeline(full_price, industry)
                            self.factor_engine.save_factors(factor_df, td)

                if not force and self._has_decision_data(dt):
                    logger.debug(f"决策已存在，跳过: {td}")
                    continue
                if force:
                    self.db.execute(f"DELETE FROM decisions WHERE trade_date = '{dt}'")
                factor_wide = self.db.fetch_df(
                    "SELECT ts_code, factor_name, factor_value FROM factors_daily WHERE trade_date = ?",
                    [dt],
                )
                if factor_wide.empty:
                    continue
                logger.info(f"[{i}/{len(trade_dates)}] 选股: {td}")
                factor_pivot = factor_wide.pivot(index="ts_code", columns="factor_name", values="factor_value")
                factor_pivot = self._pre_screen(factor_pivot, td)
                if factor_pivot.empty:
                    continue
                market_env = self._get_market_env(td)
                decision = self.reasoning.run_full_pipeline(td, factor_pivot, market_env)
                result = self.risk.validate_and_adjust(decision.get("holdings", []))
                final_holdings = result["holdings"]
                self.risk.save_decision(td, final_holdings)
            except Exception as e:
                import traceback
                logger.error(f"阶段2 {td} 失败: {e}\n{traceback.format_exc()}")
        self._is_backfill = False
        logger.info("第二阶段完成")
        if trade_dates:
            try:
                self.evolver.evaluate_performance_bulk(trade_dates)
            except Exception as e:
                logger.opt(exception=True).warning(f"绩效评估失败: {e}")
            try:
                self._auto_evolve(trade_dates[-1])
            except Exception as e:
                logger.opt(exception=True).warning(f"最终进化失败: {e}")

    def run_evolution(self, current_date: Optional[str] = None):
        if current_date is None:
            current_date = datetime.now().strftime("%Y%m%d")
        logger.info(f"触发月度进化: {current_date}")
        new_weights = self.evolver.run_monthly_evolution(current_date)
        if new_weights:
            logger.info(f"新权重(待审核): {len(new_weights)} 个因子")
        return new_weights

    def get_missing_dates(self, start_date: str, end_date: str) -> dict:
        trade_dates = self.collector.get_trade_calendar(start_date, end_date)
        existing = self.db.fetch_df(
            "SELECT DISTINCT trade_date FROM daily_price ORDER BY trade_date"
        )
        existing_set = set()
        for d in existing["trade_date"]:
            s = str(d)[:10].replace("-", "")
            existing_set.add(s)
        missing_data = [td for td in trade_dates if td not in existing_set]

        factor_existing = self.db.fetch_df(
            "SELECT DISTINCT trade_date FROM factors_daily ORDER BY trade_date"
        )
        factor_set = set()
        for d in factor_existing["trade_date"]:
            s = str(d)[:10].replace("-", "")
            factor_set.add(s)
        missing_factor = [td for td in trade_dates if td not in factor_set]

        decision_existing = self.db.fetch_df(
            "SELECT DISTINCT trade_date FROM decisions ORDER BY trade_date"
        )
        decision_set = set()
        for d in decision_existing["trade_date"]:
            s = str(d)[:10].replace("-", "")
            decision_set.add(s)
        missing_decision = [td for td in trade_dates if td not in decision_set]

        return {
            "total_trade_days": len(trade_dates),
            "missing_data": missing_data,
            "missing_factor": missing_factor,
            "missing_decision": missing_decision,
        }

    def _store_market_snapshot(self, trade_date: str):
        dt = self._to_date(trade_date)
        try:
            mkt_ret = self.db.fetch_one(
                "SELECT AVG(pct_chg)/100 FROM daily_price WHERE trade_date = ?",
                [dt],
            )
            market_return = mkt_ret[0] if mkt_ret and mkt_ret[0] else 0.0

            vol = self.db.fetch_one(
                """SELECT STDDEV(pct_chg)/100 FROM daily_price
                WHERE trade_date >= CAST(? AS DATE) - INTERVAL 20 DAY AND trade_date <= ?""",
                [dt, dt],
            )
            volatility = vol[0] if vol and vol[0] else 0.0

            breadth = self.db.fetch_one(
                "SELECT SUM(CASE WHEN pct_chg > 0 THEN 1 ELSE 0 END) * 1.0 / COUNT(*) FROM daily_price WHERE trade_date = ?",
                [dt],
            )
            breadth_val = breadth[0] if breadth and breadth[0] else 0.5

            self.memory.store_snapshot(
                trade_date=dt,
                market_return=market_return,
                volatility=volatility,
                breadth=breadth_val,
                sentiment_idx=0.0,
            )
        except Exception as e:
            logger.opt(exception=True).warning(f"市场快照存储失败: {e}")

    def _get_market_env(self, trade_date: str) -> str:
        dt = self._to_date(trade_date)
        try:
            snap = self.db.fetch_one(
                "SELECT market_return, volatility, breadth FROM market_state_snapshot WHERE snapshot_date = ?",
                [dt],
            )
            if snap:
                ret, vol, breadth = snap
                env = f"市场收益率: {ret:.2%}, 波动率: {vol:.4f}, 上涨比例: {breadth:.2%}"
            else:
                env = f"交易日期: {trade_date}"
            similar = self.memory.retrieve_similar(trade_date, top_k=3)
            if similar:
                env += f"\n历史相似日: {', '.join(d['trade_date'] for d in similar)}"
            return env
        except Exception as e:
            logger.opt(exception=True).warning(f"市场环境获取异常: {e}")
            return f"交易日期: {trade_date}"
