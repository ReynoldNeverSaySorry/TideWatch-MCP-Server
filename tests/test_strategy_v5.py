import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import tidewatch.tracker as tracker
from tidewatch.strategy import (
    aligned_return,
    direction_outcome,
    should_record_shadow_scan,
    v4_official_decision,
    v5_shadow_decision,
)


class StrategyV5Tests(unittest.TestCase):
    def test_direction_outcome_uses_final_action(self):
        self.assertEqual(direction_outcome("看多", 2.5), "correct")
        self.assertEqual(direction_outcome("看空", -2.5), "correct")
        self.assertEqual(direction_outcome("中性观望", -8.0), "abstain")

    def test_aligned_return_excludes_abstention(self):
        self.assertEqual(aligned_return("看多", 2.5), 2.5)
        self.assertEqual(aligned_return("看空", -2.5), 2.5)
        self.assertIsNone(aligned_return("中性观望", -8.0))

    def test_shadow_restores_weak_bear_outside_bull(self):
        direction, tags = v5_shadow_decision("中性观望", -32, 32, "sideways")
        self.assertEqual(direction, "看空")
        self.assertEqual(tags, ["restore_weak_bear_non_bull"])

    def test_shadow_keeps_weak_bear_neutral_in_bull(self):
        direction, tags = v5_shadow_decision("中性观望", -32, 32, "bull")
        self.assertEqual(direction, "中性观望")
        self.assertEqual(tags, [])

    def test_shadow_suppresses_official_call_in_bull(self):
        direction, tags = v5_shadow_decision("看多", 70, 70, "bull")
        self.assertEqual(direction, "中性观望")
        self.assertEqual(tags, ["bull_regime_abstain"])

    def test_v4_official_decision_contract(self):
        self.assertEqual(v4_official_decision(-32, 32, "sideways"), (
            "中性观望", ["p0_confidence_downgrade"]
        ))
        self.assertEqual(v4_official_decision(60, 60, "mild_bear"), (
            "中性观望", ["mild_bear_bull_downgrade"]
        ))
        self.assertEqual(v4_official_decision(60, 60, "bull"), ("看多", []))
        self.assertEqual(v4_official_decision(-30, 40, "mild_bull"), (
            "中性观望", ["mild_bull_bear_downgrade"]
        ))
        self.assertEqual(v4_official_decision(-35, 40, "mild_bull"), ("看空", []))

    def test_shadow_scan_gate_fails_closed(self):
        self.assertTrue(should_record_shadow_scan(0.9, "2026-09-04", "2026-09-04"))
        self.assertFalse(should_record_shadow_scan(0.89, "2026-09-04", "2026-09-04"))
        self.assertFalse(should_record_shadow_scan(1.0, "2026-09-03", "2026-09-04"))
        self.assertFalse(should_record_shadow_scan(1.0, None, "2026-09-04"))

    def test_legacy_schema_migration_preserves_rows_and_labels_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "signals.db"
            conn = sqlite3.connect(db_path)
            conn.execute("""
                CREATE TABLE signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL, name TEXT, score INTEGER, direction TEXT,
                    price_at_signal REAL, regime TEXT, confidence INTEGER,
                    reasons_bull TEXT, reasons_bear TEXT, conflicts TEXT,
                    price_5d REAL, price_10d REAL, price_20d REAL,
                    pct_5d REAL, pct_10d REAL, pct_20d REAL,
                    outcome_5d TEXT, outcome_10d TEXT, outcome_20d TEXT
                )
            """)
            conn.executemany(
                """INSERT INTO signals
                   (timestamp, symbol, score, direction, price_at_signal, pct_5d, outcome_5d)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    ("2026-05-01T18:00:00+08:00", "A", -32, "中性观望", 10, -8, "correct"),
                    ("2026-03-20T18:00:00+08:00", "B", -50, "看空", 10, -5, "correct"),
                ],
            )
            conn.commit()
            conn.close()

            with patch.object(tracker, "DB_PATH", db_path):
                migrated = tracker._get_conn()
                rows = migrated.execute(
                    "SELECT direction, action_outcome_5d, strategy_version FROM signals ORDER BY id"
                ).fetchall()
                count = migrated.execute("SELECT COUNT(*) FROM signals").fetchone()[0]
                migrated.close()

            self.assertEqual(count, 2)
            self.assertEqual(tuple(rows[0]), ("中性观望", "abstain", "v4"))
            self.assertEqual(tuple(rows[1]), ("看空", "correct", "v0"))

    def test_record_signal_persists_strategy_and_shadow_context(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "signals.db"
            with patch.object(tracker, "DB_PATH", db_path):
                signal_id = tracker.record_signal(
                    symbol="601127", name="赛力斯", score=-32, direction="中性观望",
                    price=55.0, regime="mild_bear", confidence=32,
                    reasons_bull=[], reasons_bear=["MACD绿柱"], conflicts=[],
                    raw_score=-27, strategy_version="v4", signal_source="holding",
                    decision_tags=["p0_confidence_downgrade"], shadow_direction="看空",
                    shadow_policy="v5.1-shadow", benchmark_symbol="000001",
                    benchmark_date_at_signal="2026-09-04", benchmark_price_at_signal=3800.0,
                    relative_strength_20d=-2.5,
                )
                conn = tracker._get_conn()
                row = conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
                conn.close()

            self.assertEqual(row["raw_score"], -27)
            self.assertEqual(row["signal_source"], "holding")
            self.assertEqual(row["decision_tags"], "p0_confidence_downgrade")
            self.assertEqual(row["shadow_direction"], "看空")
            self.assertEqual(row["shadow_policy"], "v5.1-shadow")
            self.assertEqual(row["benchmark_symbol"], "000001")

    def test_backfill_keeps_legacy_and_adds_action_shadow_and_benchmark_tracks(self):
        stock_dates = pd.bdate_range("2026-07-01", periods=24)
        stock_frame = pd.DataFrame({
            "date": stock_dates,
            "close": [10.0] + [10.0 - index * 0.1 for index in range(1, 24)],
        })
        benchmark_frame = pd.DataFrame({
            "date": stock_dates,
            "close": [100.0] + [100.0 + index * 0.1 for index in range(1, 24)],
        })

        class Provider:
            def get_stock_daily(self, symbol, days):
                return stock_frame.tail(days).reset_index(drop=True)

            def get_index_daily(self, symbol, days):
                return benchmark_frame.tail(days).reset_index(drop=True)

        signal_time = datetime(2026, 7, 1, 18, 0, tzinfo=timezone(timedelta(hours=8)))
        backfill_time = datetime(2026, 9, 4, 18, 0, tzinfo=timezone(timedelta(hours=8)))
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "signals.db"
            with patch.object(tracker, "DB_PATH", db_path), patch.object(
                tracker, "_now_bj", return_value=signal_time
            ):
                signal_id = tracker.record_signal(
                    symbol="601127", name="赛力斯", score=-32, direction="中性观望",
                    price=10.0, regime="mild_bear", confidence=32,
                    reasons_bull=[], reasons_bear=[], conflicts=[], shadow_direction="看空",
                    shadow_policy="v5.1-shadow", benchmark_symbol="000001",
                    benchmark_date_at_signal="2026-07-01", benchmark_price_at_signal=100.0,
                )
            with patch.object(tracker, "DB_PATH", db_path), patch.object(
                tracker, "_now_bj", return_value=backfill_time
            ):
                result = tracker.update_outcomes(Provider())
                conn = tracker._get_conn()
                row = conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
                conn.close()

        self.assertEqual(result["errors"], 0)
        self.assertEqual(row["outcome_5d"], "correct")
        self.assertEqual(row["action_outcome_5d"], "abstain")
        self.assertEqual(row["shadow_outcome_5d"], "correct")
        self.assertAlmostEqual(row["benchmark_pct_5d"], 0.5)
        self.assertAlmostEqual(row["pct_5d"], -5.0)
        self.assertAlmostEqual(row["excess_pct_5d"], -5.5)

    def test_stats_deduplicate_latest_action_and_separate_abstentions(self):
        now = datetime(2026, 9, 4, 18, 0, tzinfo=timezone(timedelta(hours=8)))
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "signals.db"
            with patch.object(tracker, "DB_PATH", db_path), patch.object(
                tracker, "_now_bj", return_value=now
            ):
                conn = tracker._get_conn()
                conn.executemany(
                    """INSERT INTO signals
                       (timestamp, symbol, score, direction, price_at_signal,
                        pct_5d, outcome_5d, action_outcome_5d)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        ("2026-09-01T10:00:00+08:00", "A", -50, "看空", 10, 2, "wrong", "wrong"),
                        ("2026-09-01T18:00:00+08:00", "A", 60, "看多", 10, 2, "correct", "correct"),
                        ("2026-09-02T18:00:00+08:00", "B", -32, "中性观望", 10, -8, "correct", "abstain"),
                    ],
                )
                conn.commit()
                conn.close()
                stats = tracker.get_signal_stats(days=30)

        self.assertEqual(stats["total_signals"], 2)
        self.assertEqual(stats["action_stats"]["5d"]["directional_filled"], 1)
        self.assertEqual(stats["action_stats"]["5d"]["hit_rate"], 100.0)
        self.assertEqual(stats["abstain_stats"]["5d"]["count"], 1)
        self.assertEqual(stats["abstain_stats"]["5d"]["avg_abs_move"], 8.0)

    def test_shadow_pool_upserts_and_backfills_from_daily_snapshots(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "signals.db"
            with patch.object(tracker, "DB_PATH", db_path):
                for index, day in enumerate(pd.bdate_range("2026-07-01", periods=21)):
                    record = {
                        "symbol": "601127", "name": "赛力斯", "signal_source": "holding",
                        "policy_version": "v5.1-shadow", "raw_score": -27,
                        "adjusted_score": -32, "confidence": 32,
                        "official_direction": "中性观望", "shadow_direction": "看空",
                        "regime": "mild_bear", "decision_tags": ["restore_weak_bear_non_bull"],
                        "price_at_signal": 10.0 - index * 0.1,
                        "benchmark_symbol": "000001",
                        "benchmark_date_at_signal": day.date().isoformat(),
                        "benchmark_price_at_signal": 100.0 + index * 0.1,
                        "relative_strength_20d": -2.0,
                    }
                    with patch.object(
                        tracker, "_now_bj",
                        return_value=day.to_pydatetime().replace(tzinfo=timezone(timedelta(hours=8))),
                    ):
                        tracker.record_shadow_scan([record], day.date().isoformat())

                tracker.record_shadow_scan([record], day.date().isoformat())
                result = tracker.update_shadow_outcomes()
                conn = tracker._get_conn()
                count = conn.execute("SELECT COUNT(*) FROM shadow_signals").fetchone()[0]
                first = conn.execute(
                    "SELECT * FROM shadow_signals ORDER BY signal_date LIMIT 1"
                ).fetchone()
                conn.close()

        self.assertEqual(count, 21)
        self.assertEqual(result, {"5d": 16, "10d": 11, "20d": 1})
        self.assertEqual(first["action_outcome_5d"], "abstain")
        self.assertEqual(first["shadow_outcome_5d"], "correct")
        self.assertEqual(first["benchmark_date_at_signal"], "2026-07-01")
        self.assertAlmostEqual(first["pct_5d"], -5.0)
        self.assertAlmostEqual(first["benchmark_pct_5d"], 0.5)
        self.assertAlmostEqual(first["excess_pct_5d"], -5.5)
        self.assertAlmostEqual(first["pct_20d"], -20.0)


if __name__ == "__main__":
    unittest.main()