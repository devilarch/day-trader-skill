#!/usr/bin/env python3
"""Unit tests for Indian Cash Equity & Option Sizer (trader-budget/size_indian.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "trader-budget")))
from size_indian import calculate_cash_equity_shares, calculate_option_lots


class TestCashEquitySizing(unittest.TestCase):
    def test_standard_cash_sizing(self):
        # Account: ₹100,000, Risk: 1.5% (₹1,500), Entry: ₹1,000, Stop: ₹950 (₹50 risk/share)
        # Shares: 1500 / 50 = 30 shares. Capital used: 30 * 1000 = ₹30,000 (30% of account)
        res = calculate_cash_equity_shares(
            capital=100000,
            risk_pct=1.5,
            entry=1000,
            stop=950,
            single_stock_cap_pct=0.35
        )
        self.assertEqual(res["shares"], 30)
        self.assertEqual(res["capital_used_inr"], 30000.0)
        self.assertEqual(res["max_risk_inr"], 1500.0)
        self.assertEqual(res["risk_pct_actual"], 1.5)
        self.assertEqual(res["status"], "APPROVED")

    def test_single_stock_cap_constraint(self):
        # Account: ₹100,000, Risk: 1.5%, Entry: ₹500, Stop: ₹495 (₹5 risk/share)
        # By risk: 1500 / 5 = 300 shares (₹150,000 capital > account).
        # By 20% single stock cap: 100000 * 0.20 = ₹20,000 -> 20000 / 500 = 40 shares.
        res = calculate_cash_equity_shares(
            capital=100000,
            risk_pct=1.5,
            entry=500,
            stop=495,
            single_stock_cap_pct=0.20
        )
        self.assertEqual(res["shares"], 40)
        self.assertEqual(res["capital_used_inr"], 20000.0)
        self.assertEqual(res["max_risk_inr"], 200.0)
        self.assertEqual(res["limiting_factor"], "single_stock_cap")
        self.assertEqual(res["status"], "APPROVED")

    def test_one_x_cash_boundary(self):
        # Account: ₹50,000, Entry: ₹1,000, Stop: ₹990 (₹10 risk/share)
        # Risk 1.5% = ₹750 -> 75 shares -> 75,000 capital.
        # Single stock cap 100% (test cash boundary): max cash = 50,000 -> 50 shares.
        res = calculate_cash_equity_shares(
            capital=50000,
            risk_pct=1.5,
            entry=1000,
            stop=990,
            single_stock_cap_pct=1.0
        )
        self.assertEqual(res["shares"], 50)
        self.assertEqual(res["capital_used_inr"], 50000.0)
        self.assertLessEqual(res["capital_used_inr"], 50000.0)
        self.assertEqual(res["limiting_factor"], "available_cash")

    def test_strict_less_than_two_pct_risk_enforcement(self):
        # Total combined risk must be strictly < 2.0% of capital.
        with self.assertRaises(ValueError) as ctx:
            calculate_cash_equity_shares(capital=100000, risk_pct=2.0, entry=100, stop=90)
        self.assertIn("strictly < 2.0%", str(ctx.exception))

    def test_invalid_stop_loss(self):
        # Stop loss at or above entry price must be rejected
        with self.assertRaises(ValueError):
            calculate_cash_equity_shares(capital=100000, risk_pct=1.0, entry=100, stop=100)
        with self.assertRaises(ValueError):
            calculate_cash_equity_shares(capital=100000, risk_pct=1.0, entry=100, stop=105)


if __name__ == "__main__":
    unittest.main()
