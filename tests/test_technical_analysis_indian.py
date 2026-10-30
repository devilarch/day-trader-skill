#!/usr/bin/env python3
"""Unit tests for Indian Market Technical S/R & Volume Engine (trader-analyst/technical_analysis_indian.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "trader-analyst")))
from technical_analysis_indian import (
    identify_sr_levels,
    analyze_volume,
    generate_technical_assessment
)


class TestTechnicalAnalysisIndian(unittest.TestCase):
    def setUp(self):
        # 30 synthetic daily candles
        # Highs cluster around 1000 (touches at candle 5, 15, 25)
        # Lows cluster around 950 (touches at candle 8, 18, 28)
        # Volume average ~ 10,000
        self.candles = []
        for i in range(30):
            c_open = 970.0
            c_close = 980.0
            c_high = 995.0
            c_low = 960.0
            c_vol = 10000.0

            if i in (5, 15, 25):
                c_high = 1000.0  # 3 touches at 1000
            if i in (8, 18, 28):
                c_low = 950.0   # 3 touches at 950

            self.candles.append({
                "open": c_open,
                "high": c_high,
                "low": c_low,
                "close": c_close,
                "volume": c_vol
            })

    def test_sr_identification_multi_touch(self):
        current_price = 980.0
        sr = identify_sr_levels(self.candles, current_price=current_price, min_touches=2)

        # Nearest resistance above 980 should be ~1000
        self.assertIsNotNone(sr["nearest_resistance"])
        self.assertAlmostEqual(sr["nearest_resistance"]["price"], 1000.0, delta=5.0)
        self.assertGreaterEqual(sr["nearest_resistance"]["touches"], 2)

        # Nearest support below 980 should be ~950
        self.assertIsNotNone(sr["nearest_support"])
        self.assertAlmostEqual(sr["nearest_support"]["price"], 950.0, delta=5.0)
        self.assertGreaterEqual(sr["nearest_support"]["touches"], 2)

    def test_volume_confirmation_high_volume(self):
        # Current volume 18,000 vs 10,000 average -> ratio 1.8 > 1.5x
        res = analyze_volume(self.candles, current_volume=18000.0, price_change_pct=1.5)
        self.assertEqual(res["volume_ratio"], 1.8)
        self.assertTrue(res["is_confirmed"])
        self.assertEqual(res["status"], "CONFIRMED_EXPANSION")

    def test_volume_confirmation_low_volume_exhaustion(self):
        # Current volume 6,000 vs 10,000 average -> ratio 0.6 < 0.8x
        res = analyze_volume(self.candles, current_volume=6000.0, price_change_pct=1.2)
        self.assertEqual(res["volume_ratio"], 0.6)
        self.assertFalse(res["is_confirmed"])
        self.assertEqual(res["status"], "EXHAUSTION_RALLY")

    def test_generate_technical_assessment_scenarios(self):
        assessment = generate_technical_assessment(
            symbol="RELIANCE",
            candles=self.candles,
            current_price=980.0,
            current_volume=16000.0
        )
        self.assertEqual(assessment["symbol"], "RELIANCE")
        self.assertIn("scenarios", assessment)
        scenarios = assessment["scenarios"]
        self.assertIn("scenario_a_bullish", scenarios)
        self.assertIn("scenario_b_bearish", scenarios)
        self.assertIn("scenario_c_sideways", scenarios)

        total_prob = (
            scenarios["scenario_a_bullish"]["probability_pct"] +
            scenarios["scenario_b_bearish"]["probability_pct"] +
            scenarios["scenario_c_sideways"]["probability_pct"]
        )
        self.assertEqual(total_prob, 100)
        self.assertIn("support_resistance", assessment)
        self.assertIn("volume_analysis", assessment)


if __name__ == "__main__":
    unittest.main()
