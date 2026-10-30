#!/usr/bin/env python3
"""Unit tests for Indian Market Standardized Action Plan Table Formatter (trader-analyst/technical_analysis_indian.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "trader-analyst")))
from technical_analysis_indian import format_action_plan_table


class TestActionPlanTableIndian(unittest.TestCase):
    def test_format_action_plan_table_with_plan_and_sizing(self):
        assessment = {
            "symbol": "RELIANCE",
            "current_price": 1250.0,
            "scenarios": {
                "scenario_a_bullish": {
                    "probability_pct": 55,
                    "trigger": "Break above ₹1,260",
                    "target": "₹1,320",
                    "invalidation": "Close below ₹1,230"
                },
                "scenario_b_bearish": {
                    "probability_pct": 25,
                    "trigger": "Break below ₹1,230",
                    "target": "₹1,180",
                    "invalidation": "Close above ₹1,260"
                },
                "scenario_c_sideways": {
                    "probability_pct": 20,
                    "range": "₹1,230 to ₹1,260",
                    "action": "Avoid mid-range chop"
                }
            }
        }
        plan = {
            "entry": 1260.0,
            "stop_loss": 1230.0,
            "target_1": 1320.0,
            "rr_t1": "2.0:1"
        }
        sizing = {
            "shares": 16,
            "max_risk_inr": 320.0
        }

        table = format_action_plan_table(assessment, plan=plan, sizing=sizing)
        self.assertIn("| Action | Trigger | Price | Size | Stop | Target | R:R |", table)
        self.assertIn("BUY / BREAKOUT", table)
        self.assertIn("₹1,260.00", table)
        self.assertIn("16 sh", table)
        self.assertIn("₹1,230.00", table)
        self.assertIn("₹1,320.00", table)
        self.assertIn("2.0:1", table)
        self.assertIn("RANGE / HOLD", table)


if __name__ == "__main__":
    unittest.main()
