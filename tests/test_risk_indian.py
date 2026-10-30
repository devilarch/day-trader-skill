#!/usr/bin/env python3
"""Unit tests for Indian Market Risk & Expected Value Gatekeeper (trader-risk/check_indian.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "trader-risk")))
from check_indian import calculate_expected_value, evaluate_rr_and_ev, check_order_risk


class TestRiskAndExpectedValue(unittest.TestCase):
    def test_calculate_expected_value_positive(self):
        # 50% win rate, ₹300 avg win, ₹100 avg loss -> EV = (0.5 * 300) - (0.5 * 100) = ₹100
        res = calculate_expected_value(win_rate=0.50, avg_win=300.0, avg_loss=100.0)
        self.assertEqual(res["ev"], 100.0)
        self.assertTrue(res["has_positive_edge"])

    def test_calculate_expected_value_negative(self):
        # 40% win rate, ₹100 avg win, ₹100 avg loss -> EV = (0.4 * 100) - (0.6 * 100) = -₹20
        res = calculate_expected_value(win_rate=0.40, avg_win=100.0, avg_loss=100.0)
        self.assertEqual(res["ev"], -20.0)
        self.assertFalse(res["has_positive_edge"])

    def test_evaluate_rr_and_ev_breakeven_thresholds(self):
        # 40% win rate requires at least (1 - 0.4)/0.4 = 1.5:1 R:R to break even.
        # Sub-breakeven trade: Entry 100, Stop 90 (Risk 10), Target 112 (Reward 12 -> 1.2:1)
        sub_be = evaluate_rr_and_ev(entry=100.0, stop=90.0, target_1=112.0, win_rate=0.40)
        self.assertFalse(sub_be["is_viable"])
        self.assertEqual(sub_be["min_breakeven_rr"], 1.5)
        self.assertEqual(sub_be["weighted_rr"], 1.2)

        # Viable trade: Target 120 (Reward 20 -> 2.0:1)
        viable = evaluate_rr_and_ev(entry=100.0, stop=90.0, target_1=120.0, win_rate=0.40)
        self.assertTrue(viable["is_viable"])
        self.assertEqual(viable["weighted_rr"], 2.0)

    def test_multi_target_weighted_rr(self):
        # Entry 100, Stop 90 (Risk 10)
        # Target 1: 110 (1R, weight 50%)
        # Target 2: 120 (2R, weight 50%)
        # Weighted R:R = (0.5 * 1.0) + (0.5 * 2.0) = 1.5:1
        res = evaluate_rr_and_ev(
            entry=100.0, stop=90.0, target_1=110.0, target_2=120.0,
            t1_weight=0.5, t2_weight=0.5, win_rate=0.50
        )
        self.assertEqual(res["weighted_rr"], 1.5)
        self.assertTrue(res["is_viable"])

    def test_check_order_risk_blocks_negative_ev_trade(self):
        # Trade risking ₹50 with only ₹10 target at 40% win rate (negative EV)
        res = check_order_risk(
            symbol="RELIANCE",
            qty=10,
            entry=1000.0,
            stop=950.0,
            target_1=1010.0,
            win_rate=0.40
        )
        self.assertEqual(res["status"], "BLOCK")
        reasons_text = " ".join(res["reasons"])
        self.assertIn("RR_EV_REJECTED", reasons_text)


if __name__ == "__main__":
    unittest.main()
