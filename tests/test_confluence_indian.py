#!/usr/bin/env python3
"""Unit tests for Indian Market 3-Screen Multi-Timeframe Confluence Engine (trader-entry/entry_indian.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "trader-entry")))
from entry_indian import evaluate_3screen_confluence


class TestConfluenceScoringIndian(unittest.TestCase):
    def setUp(self):
        # Build 30 synthetic weekly candles (solid uptrend, closes rising from 800 to 1200)
        self.weekly_candles = []
        for i in range(30):
            p = 800.0 + (i * 15.0)
            self.weekly_candles.append({
                "open": p - 5, "high": p + 10, "low": p - 10, "close": p, "volume": 50000
            })

        # Build 50 synthetic daily candles (recent close 1250, 20-DMA ~ 1200, volume 18,000 vs 10,000 avg)
        self.daily_candles = []
        for i in range(50):
            p = 1000.0 + (i * 5.0)
            vol = 10000.0
            if i >= 48:
                vol = 18000.0  # high volume surge (>1.5x)
            self.daily_candles.append({
                "open": p - 2, "high": p + 5, "low": p - 5, "close": p, "volume": vol
            })

    def test_strong_confluence_full_score(self):
        res = evaluate_3screen_confluence(
            symbol="TCS",
            weekly_candles=self.weekly_candles,
            daily_candles=self.daily_candles,
            support=1220.0,
            resistance=1280.0
        )
        self.assertGreaterEqual(res["confluence_score"], 5)
        self.assertEqual(res["rating"], "STRONG_CONFLUENCE")
        self.assertEqual(res["position_size_multiplier"], 1.0)
        self.assertEqual(res["recommendation"], "FULL_POSITION")

    def test_marginal_confluence_half_size(self):
        # Disagreeing weekly (downtrend: falling from 1200 to 800)
        down_weekly = []
        for i in range(30):
            p = 1200.0 - (i * 15.0)
            down_weekly.append({
                "open": p + 5, "high": p + 10, "low": p - 10, "close": p, "volume": 50000
            })

        # Low volume daily
        low_vol_daily = []
        for i in range(50):
            p = 900.0 + (i * 2.0)
            low_vol_daily.append({
                "open": p, "high": p + 2, "low": p - 2, "close": p, "volume": 5000
            })

        res = evaluate_3screen_confluence(
            symbol="TCS",
            weekly_candles=down_weekly,
            daily_candles=low_vol_daily,
            support=None,
            resistance=None
        )
        self.assertLessEqual(res["confluence_score"], 3)
        self.assertIn(res["rating"], ("MARGINAL_CONFLUENCE", "WEAK_NO_TRADE"))
        self.assertIn(res["position_size_multiplier"], (0.5, 0.0))

    def test_missing_weekly_candles_handled(self):
        # Empty weekly candles list shouldn't crash
        res = evaluate_3screen_confluence(
            symbol="TCS",
            weekly_candles=[],
            daily_candles=self.daily_candles
        )
        self.assertIn("confluence_score", res)
        self.assertIn("factors", res)


if __name__ == "__main__":
    unittest.main()
