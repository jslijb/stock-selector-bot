import time
import pandas as pd
import numpy as np
from loguru import logger
from datetime import datetime
from typing import Optional
import threading

try:
    import baostock as bs
    _BS_AVAILABLE = True
except ImportError:
    _BS_AVAILABLE = False


_SM_THRESHOLD = 5.0
_MD_THRESHOLD = 20.0
_LG_THRESHOLD = 100.0


class MoneyFlowEstimator:
    _login_lock = threading.Lock()
    _logged_in = False

    def __init__(self):
        self._login_attempted = False

    def _login(self):
        with MoneyFlowEstimator._login_lock:
            if MoneyFlowEstimator._logged_in:
                return True
            if not _BS_AVAILABLE:
                return False
            try:
                lg = bs.login()
                if lg.error_code == "0":
                    MoneyFlowEstimator._logged_in = True
                    return True
                logger.warning(f"baostock登录失败: {lg.error_msg}")
                return False
            except Exception as e:
                logger.opt(exception=True).warning(f"baostock登录异常: {e}")
                return False

    def _logout(self):
        with MoneyFlowEstimator._login_lock:
            if MoneyFlowEstimator._logged_in:
                try:
                    bs.logout()
                except Exception:
                    pass
                MoneyFlowEstimator._logged_in = False

    def _ts_to_baocode(self, ts_code: str) -> str:
        parts = ts_code.split(".")
        if len(parts) != 2:
            return ts_code
        code, market = parts
        prefix = "sh" if market == "SH" else "sz"
        return f"{prefix}.{code}"

    def _baocode_to_ts(self, baocode: str) -> str:
        parts = baocode.split(".")
        if len(parts) != 2:
            return baocode
        market, code = parts
        ts_market = "SH" if market == "sh" else "SZ"
        return f"{code}.{ts_market}"

    def estimate_flow_for_date(self, trade_date: str, stock_list: list = None) -> pd.DataFrame:
        if not self._login():
            logger.warning("baostock不可用，无法估算资金流向")
            return pd.DataFrame()

        date_str = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"

        if stock_list is None:
            stock_list = self._get_all_stocks()

        if not stock_list:
            return pd.DataFrame()

        results = []
        batch_size = 50
        for i in range(0, len(stock_list), batch_size):
            batch = stock_list[i:i + batch_size]
            for ts_code in batch:
                row = self._estimate_single(ts_code, date_str)
                if row is not None:
                    results.append(row)
            time.sleep(0.5)

        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df["trade_date"] = pd.to_datetime(trade_date, format="%Y%m%d")
        return df

    def _get_all_stocks(self) -> list:
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

    def _estimate_single(self, ts_code: str, date_str: str) -> Optional[dict]:
        baocode = self._ts_to_baocode(ts_code)
        try:
            rs = bs.query_history_k_data_plus(
                baocode, "time,open,high,low,close,volume,amount",
                start_date=date_str, end_date=date_str,
                frequency="5", adjustflag="3"
            )
            bars = []
            while rs.error_code == "0" and rs.next():
                row = rs.get_row_data()
                bars.append(row)

            if not bars:
                return None

            return self._classify_bars(ts_code, bars)
        except Exception:
            return None

    def _classify_bars(self, ts_code: str, bars: list) -> Optional[dict]:
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
