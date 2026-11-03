#!/usr/bin/env python3
"""Unit tests for Indian Cash Equity & Option Sizer (trader-budget/size_indian.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "trader-budget")))
from size_indian import calculate_cash_equity_shares, calculate_option_lots


class TestCashEquitySizing(unittest.TestCase):
    def test_standard_cash_sizing(self):
        # Account: ₹100,000, Risk: 1.0% (₹1,000), Entry: ₹1,000, Stop: ₹950 (₹50 risk/share)
        # Shares: 1000 / 50 = 20 shares. Capital used: 20 * 1000 = ₹20,000 (20% of account)
        res = calculate_cash_equity_shares(
            capital=100000,
            risk_pct=1.0,
            entry=1000,
            stop=950,
            single_stock_cap_pct=0.35
        )
        self.assertEqual(res["shares"], 20)
        self.assertEqual(res["capital_used_inr"], 20000.0)
        self.assertEqual(res["max_risk_inr"], 1000.0)
        self.assertEqual(res["risk_pct_actual"], 1.0)
        self.assertEqual(res["status"], "APPROVED")

    def test_single_stock_cap_constraint(self):
        # Account: ₹100,000, Risk: 1.0%, Entry: ₹500, Stop: ₹495 (₹5 risk/share)
        # By risk: 1000 / 5 = 200 shares (₹100,000 capital).
        # By 15% single stock cap: 100000 * 0.15 = ₹15,000 -> 15000 / 500 = 30 shares.
        res = calculate_cash_equity_shares(
            capital=100000,
            risk_pct=1.0,
            entry=500,
            stop=495,
            single_stock_cap_pct=0.15
        )
        self.assertEqual(res["shares"], 30)
        self.assertEqual(res["capital_used_inr"], 15000.0)
        self.assertEqual(res["max_risk_inr"], 150.0)
        self.assertEqual(res["limiting_factor"], "single_stock_cap")
        self.assertEqual(res["status"], "APPROVED")

    def test_one_x_cash_boundary(self):
        # Account: ₹50,000, Entry: ₹1,000, Stop: ₹995 (₹5 risk/share)
        # Risk 1.0% = ₹500 -> 100 shares -> 100,000 capital.
        # Single stock cap 100% (test cash boundary): max cash = 50,000 -> 50 shares.
        res = calculate_cash_equity_shares(
            capital=50000,
            risk_pct=1.0,
            entry=1000,
            stop=995,
            single_stock_cap_pct=1.0
        )
        self.assertEqual(res["shares"], 50)
        self.assertEqual(res["capital_used_inr"], 50000.0)
        self.assertLessEqual(res["capital_used_inr"], 50000.0)
        self.assertEqual(res["limiting_factor"], "available_cash")

    def test_strict_less_than_one_pct_risk_enforcement(self):
        # Total combined risk must be strictly <= 1.0% of capital.
        with self.assertRaises(ValueError) as ctx:
            calculate_cash_equity_shares(capital=100000, risk_pct=1.5, entry=100, stop=90)
        self.assertIn("strictly <= 1.0%", str(ctx.exception))

    def test_invalid_stop_loss(self):
        # Stop loss at or above entry price must be rejected
        with self.assertRaises(ValueError):
            calculate_cash_equity_shares(capital=100000, risk_pct=1.0, entry=100, stop=100)
        with self.assertRaises(ValueError):
            calculate_cash_equity_shares(capital=100000, risk_pct=1.0, entry=100, stop=105)


if __name__ == "__main__":
    unittest.main()
