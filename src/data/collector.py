import os
import time
import yaml
import tushare as ts
import pandas as pd
from loguru import logger
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from ..config import get_config
from .db import Database
from .schema import init_schema
from .money_flow import MoneyFlowEstimator
from .daily_basic_collector import DailyBasicCollector

_BS_SUPPORTED_PREFIXES = frozenset({
    "000", "001", "002", "003",
    "300", "301",
    "600", "601", "603", "605",
    "688",
})


class TushareCollector:
    def __init__(self, db: Optional[Database] = None):
        self.cfg = get_config()
        self.db = db or Database.get_instance(self.cfg.duckdb_path)
        token = os.environ.get(self.cfg.tushare_token_env)
        if not token:
            raise ValueError(f"环境变量 {self.cfg.tushare_token_env} 未设置")
        ts.set_token(token)
        self.pro = ts.pro_api()
        self._rate_delay = 60.0 / (self.cfg.tushare_rate_limit / 3.0)
        self._mf_estimator = MoneyFlowEstimator()
        self._db_collector = DailyBasicCollector()
        self._failed_dates: list = []
        self._mf_filter_cfg = None
        self._mf_financial_excludes = None

    def init_moneyflow(self, max_workers: int = 4, stock_interval: float = 1.0):
        self._mf_estimator = MoneyFlowEstimator(max_workers, stock_interval)

    def login_baostock(self):
        self._mf_estimator.ensure_login()

    def logout_baostock(self):
        self._mf_estimator.logout()

    def _rate_limit(self):
        time.sleep(self._rate_delay)

    def _ensure_init(self):
        init_schema(self.db)

    def get_trade_calendar(self, start_date: str, end_date: str) -> List[str]:
        sd = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        ed = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
        self._ensure_calendar_years(start_date[:4], end_date[:4])
        db_dates = self._read_calendar_from_db(sd, ed)
        if db_dates:
            return db_dates
        inferred = self._db_trade_calendar(start_date, end_date)
        if inferred:
            return inferred
        logger.warning("无可用交易日历，使用工作日近似(含假日)")
        return self._workday_calendar(start_date, end_date)

    def _ensure_calendar_years(self, start_year: str, end_year: str):
        init_schema(self.db)
        if not self.db.table_exists("trade_calendar"):
            self._sync_all_years(start_year, end_year)
            return
        for year in range(int(start_year), int(end_year) + 1):
            y = str(year)
            cnt = self.db.fetch_one(
                "SELECT COUNT(*) FROM trade_calendar WHERE trade_date BETWEEN ? AND ?",
                [f"{y}-01-01", f"{y}-12-31"],
            )
            if cnt is None or cnt[0] < 200:
                logger.info(f"交易日历 {y} 年不完整({cnt[0] if cnt else 0}天)，同步中...")
                self._sync_year(y)

    def _sync_year(self, year: str):
        try:
            dates = self._baostock_trade_calendar(f"{year}0101", f"{year}1231")
            if dates:
                self._save_calendar_to_db(dates)
                logger.info(f"交易日历 {year} 年同步完成: {len(dates)}天")
        except Exception as e:
            logger.opt(exception=True).warning(f"交易日历 {year} 年同步失败: {e}")

    def _sync_all_years(self, start_year: str, end_year: str):
        for year in range(int(start_year), int(end_year) + 1):
            self._sync_year(str(year))

    def _read_calendar_from_db(self, sd: str, ed: str) -> List[str]:
        try:
            if not self.db.table_exists("trade_calendar"):
                return []
            df = self.db.fetch_df(
                "SELECT trade_date FROM trade_calendar WHERE trade_date BETWEEN ? AND ? AND is_open = TRUE ORDER BY trade_date",
                [sd, ed],
            )
            if not df.empty:
                return [d.strftime("%Y%m%d") if hasattr(d, "strftime") else str(d).replace("-", "") for d in df["trade_date"]]
        except Exception:
            logger.opt(exception=True).debug("从DB读取交易日历异常")
        return []

    def _save_calendar_to_db(self, dates: List[str]):
        if not dates:
            return
        for d in dates:
            dt = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            self.db.execute(
                "INSERT OR IGNORE INTO trade_calendar (trade_date, is_open) VALUES (?, TRUE)",
                [dt],
            )

    def _db_trade_calendar(self, start_date: str, end_date: str) -> List[str]:
        sd = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        ed = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
        try:
            df = self.db.fetch_df(
                "SELECT DISTINCT trade_date FROM daily_price WHERE trade_date BETWEEN ? AND ? ORDER BY trade_date",
                [sd, ed],
            )
            if not df.empty:
                return [d.strftime("%Y%m%d") if hasattr(d, "strftime") else str(d).replace("-", "") for d in df["trade_date"]]
        except Exception:
            logger.opt(exception=True).debug("从daily_price读取交易日历异常")
        return []

    def get_industry_map(self) -> Dict[str, str]:
        self._ensure_init()
        try:
            cnt = self.db.fetch_one("SELECT COUNT(*) FROM stock_basic WHERE industry IS NOT NULL AND industry != ''")
            if cnt and cnt[0] > 0:
                df = self.db.fetch_df("SELECT ts_code, industry FROM stock_basic WHERE industry IS NOT NULL AND industry != ''")
                if not df.empty:
                    logger.info(f"从DB加载行业分类: {len(df)} 只")
                    return dict(zip(df['ts_code'], df['industry']))
        except Exception:
            logger.opt(exception=True).debug("从DB加载行业分类异常")
        try:
            full_df = self.pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,area,industry,market,list_date')
            self._rate_limit()
            if not full_df.empty:
                self._save_stock_basic_from_df(full_df)
                return dict(zip(full_df['ts_code'], full_df['industry']))
        except Exception as e:
            logger.opt(exception=True).warning(f"获取行业分类失败: {e}")
        return {}

    def _save_stock_basic_from_df(self, full_df: pd.DataFrame):
        try:
            if 'list_date' in full_df.columns:
                full_df['list_date'] = pd.to_datetime(full_df['list_date'], format='%Y%m%d', errors='coerce')
            self.db.execute("DELETE FROM stock_basic")
            temp = f"temp_stock_basic_{int(time.time()*1000)}"
            self.db.conn.register(temp, full_df)
            cols = ", ".join(full_df.columns)
            self.db.execute(f"INSERT INTO stock_basic ({cols}) SELECT {cols} FROM {temp}")
            self.db.conn.unregister(temp)
            logger.info(f"stock_basic 已持久化: {len(full_df)} 只")
        except Exception as e:
            logger.opt(exception=True).warning(f"stock_basic 持久化失败: {e}")

    def _baostock_trade_calendar(self, start_date: str, end_date: str) -> List[str]:
        import baostock as bs
        sd = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        ed = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
        lg = bs.login()
        if lg.error_code != "0":
            raise Exception(f"baostock登录失败: {lg.error_msg}")
        try:
            rs = bs.query_trade_dates(start_date=sd, end_date=ed)
            dates = []
            while rs.error_code == "0" and rs.next():
                row = rs.get_row_data()
                if len(row) > 1 and row[1] == '1':
                    dates.append(row[0].replace("-", ""))
            bs.logout()
            logger.info(f"交易日历: {start_date}~{end_date}, {len(dates)}个交易日")
            return dates
        except Exception:
            bs.logout()
            raise

    def reset_trade_calendar(self, start_year: str, end_year: str):
        logger.info(f"=== 重置交易日历 ({start_year}~{end_year}) ===")
        for year in range(int(start_year), int(end_year) + 1):
            y = str(year)
            y_sd = f"{y}-01-01"
            y_ed = f"{y}-12-31"
            cnt = self.db.fetch_one(
                "SELECT COUNT(*) FROM trade_calendar WHERE trade_date BETWEEN ? AND ?",
                [y_sd, y_ed],
            )
            if cnt and cnt[0] > 0:
                self.db.execute(
                    "DELETE FROM trade_calendar WHERE trade_date BETWEEN ? AND ?",
                    [y_sd, y_ed],
                )
                logger.info(f"已删除 {y} 年旧日历({cnt[0]}条)")
        for year in range(int(start_year), int(end_year) + 1):
            self._sync_year(str(year))

    def _workday_calendar(self, start_date: str, end_date: str) -> List[str]:
        start = datetime.strptime(start_date, "%Y%m%d")
        end = datetime.strptime(end_date, "%Y%m%d")
        dates = []
        current = start
        while current <= end:
            if current.weekday() < 5:
                dates.append(current.strftime("%Y%m%d"))
            current += timedelta(days=1)
        logger.warning(f"工作日日历(降级，含假日): {start_date}~{end_date}, {len(dates)}天")
        return dates

    def get_stock_list(self) -> pd.DataFrame:
        df = self.pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,area,industry,market,list_date")
        self._rate_limit()
        logger.info(f"获取上市股票列表: {len(df)} 只")
        return df

    def fetch_daily_price(self, trade_date: str) -> pd.DataFrame:
        df = self.pro.daily(trade_date=trade_date)
        self._rate_limit()
        if df is not None and len(df) > 0:
            df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
            self._upsert_df(df, "daily_price")
            logger.info(f"daily_price {trade_date}: {len(df)} 条")
        else:
            logger.debug(f"非交易日或无数据: {trade_date}")
        return df

    def fetch_adj_factor(self, trade_date: str) -> pd.DataFrame:
        df = self.pro.adj_factor(trade_date=trade_date)
        self._rate_limit()
        if df is not None and len(df) > 0:
            df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
            self._upsert_df(df, "adj_factor")
            logger.info(f"adj_factor {trade_date}: {len(df)} 条")
        return df

    def fetch_financials(self, period: str) -> pd.DataFrame:
        df = self.pro.income_vip(period=period, fields="ts_code,ann_date,f_ann_date,end_date,total_revenue,revenue,total_cogs,oper_cost,sell_exp,admin_exp,net_profit,n_income")
        self._rate_limit()
        if df is not None and len(df) > 0:
            df = df.rename(columns={"end_date": "report_period", "n_income": "netprofit_cut"})
            if "ann_date" in df.columns:
                df["ann_date"] = pd.to_datetime(df["ann_date"], format="%Y%m%d", errors="coerce")
            self._upsert_df(df, "financials")
            logger.info(f"financials {period}: {len(df)} 条")
        return df

    def _load_moneyflow_filter(self) -> dict:
        if self._mf_filter_cfg is not None:
            return self._mf_filter_cfg
        config_path = Path("config/moneyflow_filter.yaml")
        if not config_path.exists():
            self._mf_filter_cfg = {}
            return {}
        try:
            with open(config_path, encoding="utf-8") as f:
                self._mf_filter_cfg = yaml.safe_load(f) or {}
            logger.info(f"资金流向过滤配置已加载: {config_path}")
        except Exception as e:
            logger.warning(f"加载资金流向过滤配置失败: {e}")
            self._mf_filter_cfg = {}
        return self._mf_filter_cfg

    def _save_stock_basic_names(self, name_df: pd.DataFrame) -> None:
        if name_df.empty:
            return
        try:
            name_map = dict(zip(name_df["ts_code"], name_df["name"]))
            for ts_code, name in name_map.items():
                self.db.execute(
                    "UPDATE stock_basic SET name = ? WHERE ts_code = ?",
                    [name, ts_code],
                )
            logger.debug(f"stock_basic name列已更新: {len(name_map)} 只")
        except Exception as e:
            logger.opt(exception=True).debug(f"stock_basic name更新失败: {e}")

    def _filter_stocks_for_moneyflow(self, stock_list: list, trade_date: str) -> list:
        cfg = self._load_moneyflow_filter()
        if not cfg:
            return stock_list

        remaining = set(stock_list)
        date_param = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"

        before = len(remaining)
        remaining = {s for s in remaining if s[:3] in _BS_SUPPORTED_PREFIXES}
        if len(remaining) < before:
            logger.debug(f"过滤Baostock不支持: {before - len(remaining)} 只")

        if cfg.get("exclude_st", True):
            try:
                name_cnt = self.db.fetch_one("SELECT COUNT(*) FROM stock_basic WHERE name IS NOT NULL AND name != ''")
                if name_cnt is None or name_cnt[0] == 0:
                    try:
                        name_result = self.pro.stock_basic(
                            exchange='', list_status='L', fields='ts_code,name',
                        )
                        self._rate_limit()
                        if not name_result.empty:
                            self._save_stock_basic_names(name_result)
                            logger.info(f"已补充stock_basic name列: {len(name_result)} 只")
                    except Exception:
                        logger.opt(exception=True).debug("Tushare name数据补充异常")

                st_df = self.db.fetch_df("SELECT ts_code FROM stock_basic WHERE name LIKE '%ST%'")
                before = len(remaining)
                if not st_df.empty:
                    remaining -= set(st_df["ts_code"].tolist())
                logger.debug(f"过滤ST: {before - len(remaining)} 只")
            except Exception:
                logger.opt(exception=True).debug("ST过滤异常")

        max_price = cfg.get("max_price", 100.0)
        try:
            high_df = self.db.fetch_df(
                "SELECT ts_code FROM daily_price WHERE trade_date = ? AND close > ?",
                [date_param, max_price],
            )
            if not high_df.empty:
                before = len(remaining)
                remaining -= set(high_df["ts_code"].tolist())
                logger.debug(f"过滤高价股(>{max_price}): {before - len(remaining)} 只")
        except Exception:
            logger.opt(exception=True).debug("高价股过滤异常")

        if cfg.get("exclude_cyb", True):
            before = len(remaining)
            remaining = {s for s in remaining if not s.startswith("300")}
            logger.debug(f"过滤创业板: {before - len(remaining)} 只")

        if cfg.get("exclude_bj", True):
            before = len(remaining)
            remaining = {s for s in remaining if not s.startswith("8")}
            logger.debug(f"过滤北交所: {before - len(remaining)} 只")

        excluded = cfg.get("excluded_industries", [])
        if excluded:
            try:
                placeholders = ",".join(["?"] * len(excluded))
                ind_df = self.db.fetch_df(
                    f"SELECT ts_code FROM stock_basic WHERE industry IN ({placeholders})",
                    excluded,
                )
                if not ind_df.empty:
                    before = len(remaining)
                    remaining -= set(ind_df["ts_code"].tolist())
                    logger.debug(f"过滤黑名单行业: {before - len(remaining)} 只")
            except Exception:
                logger.opt(exception=True).debug("行业过滤异常")

        min_cap = cfg.get("min_market_cap", 100.0)
        try:
            cap_thresh = min_cap * 10000.0
            cap_df = self.db.fetch_df(
                "SELECT ts_code FROM daily_basic WHERE trade_date = ? AND total_mv < ?",
                [date_param, cap_thresh],
            )
            if not cap_df.empty:
                before = len(remaining)
                remaining -= set(cap_df["ts_code"].tolist())
                logger.debug(f"过滤小市值(<{min_cap}亿): {before - len(remaining)} 只")
        except Exception:
            logger.opt(exception=True).debug("市值过滤异常")

        if self._mf_financial_excludes is None:
            self._mf_financial_excludes = self._compute_financial_excludes(remaining, cfg)
        remaining -= self._mf_financial_excludes

        logger.info(
            f"资金流向过滤: {len(stock_list)} → {len(remaining)} 只 "
            f"(排除 {len(stock_list) - len(remaining)})"
        )
        return list(remaining)

    def _compute_financial_excludes(self, ts_codes: set, cfg: dict) -> set:
        if not ts_codes:
            return set()

        self._ensure_financials_for_filter(ts_codes)

        cyclical = set(cfg.get("cyclical_industries", []))
        try:
            ind_df = self.db.fetch_df("SELECT ts_code, industry FROM stock_basic")
            industry_map = dict(zip(ind_df["ts_code"], ind_df["industry"])) if not ind_df.empty else {}
        except Exception:
            industry_map = {}

        codes_str = ",".join([f"'{c}'" for c in ts_codes])
        try:
            fin_df = self.db.fetch_df(
                f"SELECT ts_code, report_period, net_profit, total_revenue "
                f"FROM financials WHERE ts_code IN ({codes_str})"
            )
        except Exception:
            logger.opt(exception=True).warning("财报数据查询失败，跳过财务过滤")
            return set()

        if fin_df.empty:
            logger.info("财报数据为空，跳过财务过滤")
            return set()

        now = datetime.now()
        current_year = now.year
        current_month = now.month

        if current_month <= 4:
            latest_q = (current_year - 1, 4)
        elif current_month <= 7:
            latest_q = (current_year, 1)
        elif current_month <= 10:
            latest_q = (current_year, 2)
        else:
            latest_q = (current_year, 3)
        prev_q = (latest_q[0] - 1, latest_q[1])

        q_end = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}
        latest_period = f"{latest_q[0]}{q_end[latest_q[1]]}"
        prev_period = f"{prev_q[0]}{q_end[prev_q[1]]}"

        loss_years_non = cfg.get("loss_years_noncyclical", 2)
        loss_years_cyc = cfg.get("loss_years_cyclical", 5)
        revenue_years = cfg.get("revenue_years", 2)
        min_avg_revenue = cfg.get("min_avg_revenue", 30.0) * 1e8

        excludes = set()
        for ts_code in ts_codes:
            stock_fin = fin_df[fin_df["ts_code"] == ts_code]
            if stock_fin.empty:
                continue

            latest_np_row = stock_fin[stock_fin["report_period"] == latest_period]
            prev_np_row = stock_fin[stock_fin["report_period"] == prev_period]

            if not latest_np_row.empty and not prev_np_row.empty:
                latest_np = latest_np_row["net_profit"].iloc[0]
                prev_np = prev_np_row["net_profit"].iloc[0]
                if pd.notna(latest_np) and pd.notna(prev_np) and latest_np > 0:
                    if prev_np <= 0:
                        continue
                    growth = (latest_np - prev_np) / abs(prev_np)
                    if growth >= 0.1:
                        continue

            industry = industry_map.get(ts_code, "")
            is_cyclical = industry in cyclical
            n_years = loss_years_cyc if is_cyclical else loss_years_non

            annual = stock_fin[stock_fin["report_period"].str.endswith("1231")]
            annual = annual.sort_values("report_period", ascending=False).head(n_years)
            if len(annual) >= n_years and (annual["net_profit"] < 0).all():
                excludes.add(ts_code)
                continue

            rev_annual = annual.head(revenue_years)
            if len(rev_annual) >= revenue_years:
                avg_rev = rev_annual["total_revenue"].mean()
                if pd.notna(avg_rev) and avg_rev < min_avg_revenue:
                    excludes.add(ts_code)

        if excludes:
            logger.info(f"财务过滤排除 {len(excludes)} 只(连续亏损/低营收)")
        else:
            logger.debug("财务过滤: 无排除")
        return excludes

    def _ensure_financials_for_filter(self, ts_codes: set) -> None:
        if not ts_codes:
            return
        if not self._mf_estimator._logged_in:
            logger.warning("baostock未登录，跳过财报数据补充")
            return

        cfg = self._load_moneyflow_filter()
        cyclical = set(cfg.get("cyclical_industries", []))
        try:
            ind_df = self.db.fetch_df("SELECT ts_code, industry FROM stock_basic")
            industry_map = dict(zip(ind_df["ts_code"], ind_df["industry"])) if not ind_df.empty else {}
        except Exception:
            industry_map = {}

        now = datetime.now()
        current_year = now.year
        current_month = now.month
        if current_month <= 4:
            latest_q = (current_year - 1, 4)
        elif current_month <= 7:
            latest_q = (current_year, 1)
        elif current_month <= 10:
            latest_q = (current_year, 2)
        else:
            latest_q = (current_year, 3)
        prev_q = (latest_q[0] - 1, latest_q[1])

        q_end = {1: "0331", 2: "0630", 3: "0930", 4: "1231"}
        quarterly_periods = [
            f"{latest_q[0]}{q_end[latest_q[1]]}",
            f"{prev_q[0]}{q_end[prev_q[1]]}",
        ]

        loss_years_non = cfg.get("loss_years_noncyclical", 2)
        loss_years_cyc = cfg.get("loss_years_cyclical", 5)
        revenue_years = cfg.get("revenue_years", 2)

        required = {}
        for ts_code in ts_codes:
            industry = industry_map.get(ts_code, "")
            n = loss_years_cyc if industry in cyclical else loss_years_non
            n = max(n, revenue_years)
            periods = [f"{y}1231" for y in range(current_year - n, current_year)]
            periods.extend(quarterly_periods)
            required[ts_code] = periods

        codes_str = ",".join([f"'{c}'" for c in ts_codes])
        try:
            existing_df = self.db.fetch_df(
                f"SELECT DISTINCT ts_code, report_period FROM financials "
                f"WHERE ts_code IN ({codes_str})"
            )
            existing = set(zip(existing_df["ts_code"], existing_df["report_period"])) if not existing_df.empty else set()
        except Exception:
            existing = set()

        missing = []
        for ts_code, periods in required.items():
            for period in periods:
                if (ts_code, period) not in existing:
                    missing.append((ts_code, period))

        if not missing:
            logger.info("财报数据完整，无需补充")
            return

        logger.info(f"需补充财报数据: {len(missing)} 条, 预计耗时 {len(missing) * 0.15:.0f} 秒")

        new_rows = []
        fetched = 0
        for ts_code, period in missing:
            year = int(period[:4])
            month = int(period[4:6])
            if month <= 3:
                quarter = 1
            elif month <= 6:
                quarter = 2
            elif month <= 9:
                quarter = 3
            else:
                quarter = 4

            baocode = MoneyFlowEstimator._ts_to_baocode(ts_code)
            data = self._mf_estimator.query_profit_data(baocode, year, quarter)
            if data:
                try:
                    net_profit = float(data.get("netProfit", 0))
                    total_revenue = float(data.get("totalOperRev", 0))
                    new_rows.append({
                        "ts_code": ts_code,
                        "report_period": period,
                        "net_profit": net_profit,
                        "total_revenue": total_revenue,
                    })
                except (ValueError, TypeError):
                    pass

            fetched += 1
            if fetched % 100 == 0:
                logger.info(f"财报补充进度: {fetched}/{len(missing)}")
            time.sleep(0.15)

        if new_rows:
            df = pd.DataFrame(new_rows)
            self._upsert_df(df, "financials")
            logger.info(f"财报数据补充完成: {len(new_rows)} 条")

    def fetch_money_flow(self, trade_date: str) -> pd.DataFrame:
        logger.info(f"baostock分钟线估算资金流向: {trade_date}")
        stock_list = None
        suspended = None
        try:
            date_param = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
            price_df = self.db.fetch_df(
                "SELECT DISTINCT ts_code FROM daily_price WHERE trade_date = ?",
                [date_param],
            )
            if not price_df.empty:
                stock_list = price_df["ts_code"].tolist()

            susp_df = self.db.fetch_df(
                "SELECT ts_code FROM daily_price WHERE trade_date = ? AND vol = 0",
                [date_param],
            )
            if not susp_df.empty:
                suspended = set(susp_df["ts_code"].tolist())
        except Exception:
            logger.opt(exception=True).debug("获取资金流股票列表异常")

        if stock_list:
            stock_list = self._filter_stocks_for_moneyflow(stock_list, trade_date)

        df = self._mf_estimator.estimate_flow_for_date(trade_date, stock_list, suspended)
        if not df.empty:
            self._upsert_df(df, "money_flow")
            logger.info(f"money_flow {trade_date}: {len(df)} 条")
        return df

    def fetch_daily_basic(self, trade_date: str) -> pd.DataFrame:
        dt = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        try:
            cnt = self.db.fetch_one(
                "SELECT COUNT(*) FROM daily_basic WHERE trade_date = ?", [dt]
            )
            if cnt and cnt[0] > 0:
                logger.debug(f"daily_basic已存在，跳过: {trade_date}")
                return pd.DataFrame()
        except Exception:
            logger.opt(exception=True).debug("daily_basic存在性检查异常")

        logger.info(f"baostock获取每日指标: {trade_date}")
        stock_list = None
        try:
            price_df = self.db.fetch_df(
                "SELECT DISTINCT ts_code FROM daily_price WHERE trade_date = ?",
                [dt],
            )
            if not price_df.empty:
                stock_list = price_df["ts_code"].tolist()
        except Exception:
            logger.opt(exception=True).debug("获取每日指标股票列表异常")

        df = self._db_collector.fetch_daily_basic(trade_date, stock_list)
        if not df.empty:
            self._upsert_df(df, "daily_basic")
            logger.info(f"daily_basic {trade_date}: {len(df)} 条")

        if self.cfg.risk.enable_bj:
            try:
                bj_cnt = self.db.fetch_one(
                    "SELECT COUNT(*) FROM daily_basic WHERE trade_date = ? AND ts_code LIKE '%.BJ'",
                    [dt],
                )
                if bj_cnt is None or bj_cnt[0] == 0:
                    bj_df = self._db_collector.fetch_bj_daily_basic(trade_date)
                    if not bj_df.empty:
                        self._upsert_df(bj_df, "daily_basic")
                        logger.info(f"北交所daily_basic {trade_date}: {len(bj_df)} 条")
            except Exception as e:
                logger.opt(exception=True).warning(f"北交所每日指标采集失败: {e}")

        return df

    def _has_daily_data(self, trade_date: str) -> bool:
        dt = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        try:
            cnt = self.db.fetch_one(
                "SELECT COUNT(*) FROM daily_price WHERE trade_date = ?", [dt]
            )
            return cnt is not None and cnt[0] > 0
        except Exception:
            logger.opt(exception=True).debug("日线数据检查异常")
            return False

    def _is_weekend(self, trade_date: str) -> bool:
        dt = datetime.strptime(trade_date, "%Y%m%d")
        return dt.weekday() >= 5

    def run_daily(self, trade_date: str, skip_money_flow: bool = False):
        self._ensure_init()
        if self._is_weekend(trade_date):
            return
        if self._has_daily_data(trade_date):
            logger.debug(f"数据已存在，跳过采集: {trade_date}")
            return
        logger.info(f"=== 采集日线数据: {trade_date} ===")
        price_df = None
        try:
            price_df = self.fetch_daily_price(trade_date)
        except Exception as e:
            logger.opt(exception=True).error(f"日线行情采集失败 {trade_date}: {e}")
            self._failed_dates.append(trade_date)
            return
        if price_df is None or (isinstance(price_df, pd.DataFrame) and price_df.empty):
            logger.debug(f"无日线数据(非交易日或采集失败)，跳过后续: {trade_date}")
            return
        try:
            self.fetch_adj_factor(trade_date)
        except Exception as e:
            logger.opt(exception=True).debug(f"复权因子采集跳过 {trade_date}: {e}")
        if not skip_money_flow:
            try:
                self.fetch_money_flow(trade_date)
            except Exception as e:
                logger.opt(exception=True).warning(f"资金流向采集失败 {trade_date}: {e}")

    def get_failed_dates(self) -> list:
        return self._failed_dates

    def run_backfill(self, start_date: str, end_date: str):
        self._ensure_init()
        trade_dates = self.get_trade_calendar(start_date, end_date)
        existing_min, existing_max = self.db.get_date_range("daily_price")

        for td in trade_dates:
            if existing_min and existing_max:
                td_dt = datetime.strptime(td, "%Y%m%d")
                if existing_min <= td_dt <= existing_max:
                    logger.debug(f"跳过已存在日期: {td}")
                    continue
            self.run_daily(td)
        logger.info(f"补跑完成: {start_date} ~ {end_date}")

    def _upsert_df(self, df: pd.DataFrame, table_name: str):
        date_val = None
        if "trade_date" in df.columns:
            dates = df["trade_date"].unique()
            if len(dates) == 1:
                d = dates[0]
                date_val = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
        temp_view = f"temp_{table_name}_{int(time.time()*1000)}"
        self.db.conn.register(temp_view, df)
        cols = ", ".join(df.columns)
        try:
            if date_val:
                self.db.locked_execute(
                    table_name, date_val,
                    f"INSERT OR IGNORE INTO {table_name} ({cols}) SELECT {cols} FROM {temp_view}",
                )
            else:
                self.db.execute(f"INSERT OR IGNORE INTO {table_name} ({cols}) SELECT {cols} FROM {temp_view}")
        except Exception as e:
            logger.opt(exception=True).error(f"写入 {table_name} 失败: {e}")
            raise
        finally:
            try:
                self.db.conn.unregister(temp_view)
            except Exception as e:
                logger.opt(exception=True).warning(f"临时视图 {temp_view} 注销失败(不影响数据): {e}")
