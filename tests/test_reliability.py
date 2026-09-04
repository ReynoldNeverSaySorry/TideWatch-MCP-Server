import time
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import numpy as np

import tidewatch.data as data
import tidewatch.server as server
from scripts.validate_scan_response import validate


def reset_bs_state():
    data._bs_logged_in = False
    data._bs_login_time = 0
    data._bs_circuit_open_until = 0


class ReliabilityTests(unittest.TestCase):
    def test_daily_scan_gate(self):
        current = {
            "meta": {"market_data_date": "2026-08-06", "source": ["yfinance"]},
            "pool_size": {"scanned": 32, "total": 32},
        }
        self.assertEqual(validate(current, "2026-08-06")[0], 0)

        low_coverage = {
            "meta": {"market_data_date": "2026-08-06", "source": ["yfinance"]},
            "pool_size": {"scanned": 20, "total": 32},
        }
        self.assertEqual(validate(low_coverage, "2026-08-06")[0], 1)

        holiday = {
            "meta": {"market_data_date": "2026-08-05", "source": ["yfinance"]},
            "pool_size": {"scanned": 32, "total": 32},
        }
        self.assertEqual(validate(holiday, "2026-08-06")[0], 3)

        stale_local = {
            "meta": {"market_data_date": "2026-08-05", "source": ["local_cache"]},
            "pool_size": {"scanned": 32, "total": 32},
        }
        self.assertEqual(validate(stale_local, "2026-08-06")[0], 1)

    def test_expected_market_date_respects_preopen_and_weekend(self):
        tz = server._BJ_TZ
        self.assertEqual(server._expected_market_data_date(datetime(2026, 8, 7, 0, 10, tzinfo=tz)), "2026-08-06")
        self.assertEqual(server._expected_market_data_date(datetime(2026, 8, 10, 8, 30, tzinfo=tz)), "2026-08-07")
        self.assertEqual(server._expected_market_data_date(datetime(2026, 8, 10, 10, 0, tzinfo=tz)), "2026-08-10")
        self.assertEqual(server._expected_market_data_date(datetime(2026, 8, 9, 12, 0, tzinfo=tz)), "2026-08-07")

    def test_expected_market_date_defaults_to_current_beijing_time(self):
        now = datetime(2026, 9, 4, 14, 0, tzinfo=server._BJ_TZ)
        with patch.object(server, "_now_bj", return_value=now):
            self.assertEqual(server._expected_market_data_date(), "2026-09-04")

    def test_json_safe_converts_numpy_scalars(self):
        value = {
            "flag": np.bool_(True), "score": np.int64(7), "ratio": np.float64(1.5),
            "time": pd.Timestamp("2026-08-06"),
        }
        result = server._json_safe(value)
        self.assertIs(result["flag"], True)
        self.assertEqual(result["score"], 7)
        self.assertEqual(result["ratio"], 1.5)
        self.assertEqual(result["time"], "2026-08-06T00:00:00")

    def test_dataframe_source_survives_slice(self):
        frame = pd.DataFrame({"close": [1.0, 2.0]})
        frame.attrs["source"] = "probe"
        sliced = frame.tail(1).reset_index(drop=True)
        self.assertEqual(sliced.attrs["source"], "probe")

    def test_yahoo_a_share_ticker_mapping(self):
        self.assertEqual(data._to_yahoo_a_ticker("601127"), "601127.SS")
        self.assertEqual(data._to_yahoo_a_ticker("002111"), "002111.SZ")
        self.assertEqual(data._to_yahoo_a_ticker("512400"), "512400.SS")

    def test_a_share_uses_yfinance_before_akshare(self):
        expected = pd.DataFrame({
            "date": pd.to_datetime(["2026-08-06"]), "open": [10.0], "high": [11.0],
            "low": [9.5], "close": [10.8], "volume": [100], "pct_change": [2.0],
        })
        market = data.MarketData()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            data, "_MARKET_CACHE_DIR", Path(directory)
        ), patch.object(data, "_bs_login", side_effect=data.ProviderUnavailable("blocked")), patch.object(
            data, "_get_yfinance_a_daily", return_value=expected
        ), patch.object(data, "_get_a_share_daily_fallback") as ak_fallback:
            actual = market.get_stock_daily("601127", days=120)
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual.iloc[0]["close"], 10.8)
        ak_fallback.assert_not_called()

    def test_etf_uses_yfinance_before_etf_akshare(self):
        expected = pd.DataFrame({
            "date": pd.to_datetime(["2026-08-06"]), "open": [1.9], "high": [1.93],
            "low": [1.88], "close": [1.917], "volume": [100], "pct_change": [0.8],
        })
        market = data.MarketData()
        with tempfile.TemporaryDirectory() as directory, patch.object(
            data, "_MARKET_CACHE_DIR", Path(directory)
        ), patch.object(data, "_bs_login", side_effect=data.ProviderUnavailable("blocked")), patch.object(
            data, "_get_yfinance_a_daily", return_value=expected
        ), patch.object(data.ak, "fund_etf_hist_em") as etf_fallback:
            actual = market.get_stock_daily("512400", days=120)
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual.iloc[0]["close"], 1.917)
        etf_fallback.assert_not_called()

    def test_blacklist_opens_circuit_and_suppresses_relogin(self):
        reset_bs_state()
        calls = []

        def blocked_login():
            calls.append(1)
            return SimpleNamespace(error_code="1", error_msg="黑名单用户，请与管理员联系")

        with patch.object(data.bs, "login", blocked_login), patch.object(
            data, "_force_close_bs_socket", lambda: setattr(data, "_bs_logged_in", False)
        ):
            for _ in range(2):
                with self.assertRaises(data.ProviderUnavailable):
                    data._bs_login()

        self.assertEqual(len(calls), 1)
        self.assertGreater(data._bs_circuit_remaining(), 1700)

    def test_daily_cache_round_trip(self):
        frame = pd.DataFrame({
            "date": pd.to_datetime(["2026-08-04", "2026-08-05"]),
            "open": [10.0, 10.5], "high": [11.0, 11.2], "low": [9.8, 10.1],
            "close": [10.6, 11.0], "volume": [100, 120], "pct_change": [1.0, 3.8],
        })
        with tempfile.TemporaryDirectory() as directory, patch.object(
            data, "_MARKET_CACHE_DIR", Path(directory)
        ):
            data._write_daily_cache("601127", frame)
            restored = data._read_daily_cache("601127", 1)
            self.assertEqual(len(restored), 1)
            self.assertEqual(restored.iloc[0]["close"], 11.0)
            self.assertTrue(Path(directory, "601127.csv").exists())

    def test_dashboard_session_round_trip(self):
        with patch.object(server, "DASHBOARD_AUTH_DISABLED", False), patch.object(
            server, "DASHBOARD_SESSION_SECRET", "test-session-secret"
        ):
            token = server._create_dashboard_session()
            self.assertTrue(server._verify_dashboard_session(token))
            self.assertFalse(server._verify_dashboard_session(token + "tampered"))

    def test_scan_singleflight_reuses_existing_snapshot(self):
        old_cache = server._scan_cache
        server._scan_cache = {"result": {"timestamp": server._now_bj().isoformat()}, "time": 0}
        acquired = server._scan_run_lock.acquire(blocking=False)
        self.assertTrue(acquired)
        try:
            self.assertFalse(server._run_scan_warmup())
        finally:
            server._scan_run_lock.release()
            server._scan_cache = old_cache

    def test_detail_fallback_rejects_cache_older_than_72_hours(self):
        old_cache = server._scan_cache
        server._scan_cache = {
            "result": {
                "timestamp": (server._now_bj() - timedelta(hours=73)).isoformat(),
                "holdings": [{"code": "601127", "name": "赛力斯", "score": 33}],
            },
            "time": 0,
        }
        try:
            self.assertIsNone(server._build_scan_cache_fallback("601127"))
        finally:
            server._scan_cache = old_cache

    def test_scan_meta_marks_intraday_old_snapshot_stale(self):
        old_cache = server._scan_cache
        timestamp = (server._now_bj() - timedelta(minutes=6)).isoformat()
        server._scan_cache = {
            "result": {
                "timestamp": timestamp, "_hot_sorted": [], "holdings": [], "watchlist": [],
                "market_data_date": server._now_bj().date().isoformat(),
                "pool_size": {"scanned": 0, "total": 0},
            },
            "time": time.monotonic(),
        }
        try:
            with patch.object(server, "_is_market_hours", return_value=True):
                result = server._slice_scan_cache(5)
            self.assertEqual(result["meta"]["status"], "stale")
            self.assertGreaterEqual(result["meta"]["age_seconds"], 6 * 60 - 2)
        finally:
            server._scan_cache = old_cache

    def test_scan_meta_keeps_today_close_fresh_after_market(self):
        old_cache = server._scan_cache
        fixed_now = datetime(2026, 8, 6, 18, 0, tzinfo=server._BJ_TZ)
        server._scan_cache = {
            "result": {
                "timestamp": (fixed_now - timedelta(hours=6)).isoformat(),
                "market_data_date": fixed_now.date().isoformat(),
                "_hot_sorted": [], "holdings": [], "watchlist": [],
                "pool_size": {"scanned": 32, "total": 32},
            },
            "time": 0,
        }
        try:
            with patch.object(server, "_now_bj", return_value=fixed_now), patch.object(
                server, "_is_market_hours", return_value=False
            ):
                result = server._slice_scan_cache(5)
            self.assertEqual(result["meta"]["status"], "fresh")
        finally:
            server._scan_cache = old_cache


if __name__ == "__main__":
    unittest.main()
