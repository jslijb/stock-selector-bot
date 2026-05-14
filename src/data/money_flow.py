import time
import threading
import pandas as pd
import numpy as np
from loguru import logger
from datetime import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

try:
    import baostock as bs
    _BS_AVAILABLE = True
except ImportError:
    _BS_AVAILABLE = False


_SM_THRESHOLD = 5.0
_MD_THRESHOLD = 20.0
_LG_THRESHOLD = 100.0


class MoneyFlowEstimator:
    _bs_lock = threading.Lock()
    _logged_in = False

    def __init__(self, max_workers: int = 4, stock_interval: float = 1.0):
        self.max_workers = max_workers
        self.stock_interval = stock_interval

    def ensure_login(self):
        if not _BS_AVAILABLE:
            return
        with self._bs_lock:
            if not self._logged_in:
                lg = bs.login()
                if lg.error_code != "0":
                    logger.warning(f"baostock登录失败: {lg.error_msg}")
                else:
                    self._logged_in = True
                    logger.debug("baostock登录成功")

    def logout(self):
        with self._bs_lock:
            if self._logged_in:
                try:
                    bs.logout()
                except Exception as e:
                    logger.debug(f"baostock登出异常: {e}")
                self._logged_in = False

    def _bs_query(self, baocode: str, date_str: str) -> Optional[list]:
        with self._bs_lock:
            if not self._logged_in:
                return None
            rs = bs.query_history_k_data_plus(
                baocode, "time,open,high,low,close,volume,amount",
                start_date=date_str, end_date=date_str,
                frequency="5", adjustflag="3",
            )
            if rs.error_code != "0":
                return None
            bars = []
            while rs.next():
                row = rs.get_row_data()
                bars.append(row)
            return bars if bars else None

    @staticmethod
    def _ts_to_baocode(ts_code: str) -> str:
        parts = ts_code.split(".")
        if len(parts) != 2:
            return ts_code
        code, market = parts
        prefix = "sh" if market == "SH" else "sz"
        return f"{prefix}.{code}"

    @staticmethod
    def _baocode_to_ts(baocode: str) -> str:
        parts = baocode.split(".")
        if len(parts) != 2:
            return baocode
        market, code = parts
        ts_market = "SH" if market == "sh" else "SZ"
        return f"{code}.{ts_market}"

    def estimate_flow_for_date(self, trade_date: str, stock_list: list = None) -> pd.DataFrame:
        if not _BS_AVAILABLE:
            logger.warning("baostock不可用，无法估算资金流向")
            return pd.DataFrame()

        date_str = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"

        if stock_list is None:
            stock_list = self._get_all_stocks()

        if not stock_list:
            return pd.DataFrame()

        chunk_size = max(1, len(stock_list) // self.max_workers)
        chunks = [stock_list[i:i + chunk_size] for i in range(0, len(stock_list), chunk_size)]

        failed_stocks: list = []
        failed_lock = threading.Lock()
        all_results: list = []

        def worker(stock_batch: list) -> list:
            local_results = []
            local_failed = []
            for ts_code in stock_batch:
                try:
                    bars = self._bs_query(self._ts_to_baocode(ts_code), date_str)
                    if bars:
                        row = self._classify_bars(ts_code, bars)
                        if row:
                            local_results.append(row)
                            continue
                    local_failed.append(ts_code)
                except Exception as e:
                    local_failed.append(ts_code)
                    logger.opt(exception=True).debug(f"资金流向 {ts_code} 异常: {e}")
                time.sleep(self.stock_interval)
            if local_failed:
                with failed_lock:
                    failed_stocks.extend(local_failed)
            return local_results

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(worker, chunk) for chunk in chunks]
            for f in futures:
                try:
                    chunk_results = f.result()
                    all_results.extend(chunk_results)
                except Exception as e:
                    logger.error(f"资金流向线程执行异常: {e}")

        if failed_stocks:
            logger.warning(
                f"资金流向获取失败 {len(failed_stocks)} 只: "
                f"{failed_stocks[:20]}{'...' if len(failed_stocks) > 20 else ''}"
            )

        if not all_results:
            return pd.DataFrame()

        df = pd.DataFrame(all_results)
        df["trade_date"] = pd.to_datetime(trade_date, format="%Y%m%d")
        return df

    def _get_all_stocks(self) -> list:
        if not _BS_AVAILABLE:
            return []
        with self._bs_lock:
            if not self._logged_in:
                return []
            try:
                rs = bs.query_stock_basic()
                stocks = []
                while rs.error_code == "0" and rs.next():
                    row = rs.get_row_data()
                    code = row[0]
                    if code.startswith(("sh.6", "sz.0", "sz.3")):
                        stocks.append(self._baocode_to_ts(code))
                return stocks
            except Exception as e:
                logger.warning(f"获取股票列表失败: {e}")
                return []

    @staticmethod
    def _classify_bars(ts_code: str, bars: list) -> Optional[dict]:
        total_buy_sm_amount = 0.0
        total_sell_sm_amount = 0.0
        total_buy_sm_vol = 0
        total_sell_sm_vol = 0
        total_buy_md_amount = 0.0
        total_sell_md_amount = 0.0
        total_buy_md_vol = 0
        total_sell_md_vol = 0
        total_buy_lg_amount = 0.0
        total_sell_lg_amount = 0.0
        total_buy_lg_vol = 0
        total_sell_lg_vol = 0
        total_buy_elg_amount = 0.0
        total_sell_elg_amount = 0.0
        total_buy_elg_vol = 0
        total_sell_elg_vol = 0

        for bar in bars:
            try:
                open_p = float(bar[1])
                close_p = float(bar[4])
                vol = float(bar[5])
                amount = float(bar[6])
            except (ValueError, IndexError):
                continue

            if vol <= 0 or amount <= 0:
                continue

            amount_wan = amount / 10000.0
            vol_hand = vol / 100.0

            is_buy = close_p >= open_p

            if amount_wan >= _LG_THRESHOLD:
                if is_buy:
                    total_buy_elg_amount += amount_wan
                    total_buy_elg_vol += vol_hand
                else:
                    total_sell_elg_amount += amount_wan
                    total_sell_elg_vol += vol_hand
            elif amount_wan >= _MD_THRESHOLD:
                if is_buy:
                    total_buy_lg_amount += amount_wan
                    total_buy_lg_vol += vol_hand
                else:
                    total_sell_lg_amount += amount_wan
                    total_sell_lg_vol += vol_hand
            elif amount_wan >= _SM_THRESHOLD:
                if is_buy:
                    total_buy_md_amount += amount_wan
                    total_buy_md_vol += vol_hand
                else:
                    total_sell_md_amount += amount_wan
                    total_sell_md_vol += vol_hand
            else:
                if is_buy:
                    total_buy_sm_amount += amount_wan
                    total_buy_sm_vol += vol_hand
                else:
                    total_sell_sm_amount += amount_wan
                    total_sell_sm_vol += vol_hand

        net_mf_vol = (total_buy_sm_vol + total_buy_md_vol + total_buy_lg_vol + total_buy_elg_vol) - \
                     (total_sell_sm_vol + total_sell_md_vol + total_sell_lg_vol + total_sell_elg_vol)
        net_mf_amount = (total_buy_sm_amount + total_buy_md_amount + total_buy_lg_amount + total_buy_elg_amount) - \
                        (total_sell_sm_amount + total_sell_md_amount + total_sell_lg_amount + total_sell_elg_amount)

        return {
            "ts_code": ts_code,
            "buy_sm_vol": total_buy_sm_vol,
            "buy_sm_amount": total_buy_sm_amount,
            "sell_sm_vol": total_sell_sm_vol,
            "sell_sm_amount": total_sell_sm_amount,
            "buy_lg_vol": total_buy_lg_vol + total_buy_elg_vol,
            "buy_lg_amount": total_buy_lg_amount + total_buy_elg_amount,
            "sell_lg_vol": total_sell_lg_vol + total_sell_elg_vol,
            "sell_lg_amount": total_sell_lg_amount + total_sell_elg_amount,
            "net_mf_vol": net_mf_vol,
            "net_mf_amount": net_mf_amount,
        }