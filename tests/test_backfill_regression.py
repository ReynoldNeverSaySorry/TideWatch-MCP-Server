import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

import tidewatch.data as data
import tidewatch.server as server


class BackfillRegressionTests(unittest.TestCase):
    def test_a_share_backfill_uses_supplied_market_data(self):
        expected = pd.DataFrame({
            "date": pd.to_datetime(["2026-08-05", "2026-08-06"]),
            "open": [10.0, 10.5],
            "high": [11.0, 11.2],
            "low": [9.8, 10.1],
            "close": [10.6, 11.0],
            "volume": [100, 120],
            "pct_change": [1.0, 3.8],
        })
        calls = []

        def get_stock_daily(symbol, days):
            calls.append((symbol, days))
            return expected

        provider = SimpleNamespace(get_stock_daily=get_stock_daily)
        actual = data.get_stock_daily_for_backfill(
            "601127", days=2, market_data=provider
        )

        self.assertEqual(calls, [("601127", 2)])
        self.assertEqual(list(actual.columns), ["date", "close"])
        self.assertEqual(actual.iloc[-1]["close"], 11.0)

    def test_backfill_errors_are_exposed_to_callers(self):
        failed = {"5d": 0, "10d": 0, "20d": 0, "errors": 3}
        with patch.object(server, "update_outcomes", return_value=failed):
            result = asyncio.run(server.update_signal_outcomes())

        self.assertTrue(result["degraded"])
        self.assertIn("3 条信号处理失败", result["error"])


if __name__ == "__main__":
    unittest.main()