#!/usr/bin/env python3
"""Unit tests for Indian Market Exit & Trailing Stop Planner (trader-exit/exit_indian.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "trader-exit")))
from exit_indian import calculate_trailing_stop, plan_exit


class TestExitAndTrailingStop(unittest.TestCase):
    def test_stage_1_fixed_initial_stop(self):
        # Entry: 100, Stop: 90 -> 1R = 10
        # Current: 105, Highest: 105 (Gain: 0.5R < 1R)
        res = calculate_trailing_stop(entry=100.0, initial_stop=90.0, current_price=105.0, highest_price=105.0)
        self.assertEqual(res["trailing_stop"], 90.0)
        self.assertEqual(res["stage"], 1)
        self.assertEqual(res["stage_name"], "Fixed Initial Stop")
        self.assertEqual(res["r_multiple_gained"], 0.5)

    def test_stage_2_breakeven_at_1r(self):
        # Current: 110, Highest: 110 (Gain: 1.0R)
        res = calculate_trailing_stop(entry=100.0, initial_stop=90.0, current_price=110.0, highest_price=110.0)
        self.assertEqual(res["trailing_stop"], 100.0)
        self.assertEqual(res["stage"], 2)
        self.assertEqual(res["stage_name"], "Breakeven")
        self.assertEqual(res["r_multiple_gained"], 1.0)

    def test_stage_3_atr_trail_at_2r(self):
        # Current: 122, Highest: 125 (Gain: 2.5R >= 2.0R), ATR = 4.0
        # Trail = 125 - (1.5 * 4.0) = 119.0
        res = calculate_trailing_stop(
            entry=100.0, initial_stop=90.0, current_price=122.0, highest_price=125.0, atr=4.0
        )
        self.assertEqual(res["trailing_stop"], 119.0)
        self.assertEqual(res["stage"], 3)
        self.assertEqual(res["stage_name"], "ATR Trail")

    def test_stage_4_structure_trail_at_3r(self):
        # Current: 135, Highest: 136 (Gain: 3.6R >= 3.0R), swing_low = 131.0
        res = calculate_trailing_stop(
            entry=100.0, initial_stop=90.0, current_price=135.0, highest_price=136.0, atr=4.0, swing_low=131.0
        )
        self.assertEqual(res["trailing_stop"], 131.0)
        self.assertEqual(res["stage"], 4)
        self.assertEqual(res["stage_name"], "Structure Trail")

    def test_ratchet_never_moves_backward(self):
        # Price hit 125 earlier (ATR stop was 119), now current price pulls back to 116.
        # Trailing stop must remain at highest ratcheted level (119.0), not move down.
        res = calculate_trailing_stop(
            entry=100.0, initial_stop=90.0, current_price=116.0, highest_price=125.0, atr=4.0
        )
        self.assertGreaterEqual(res["trailing_stop"], 119.0)

    def test_plan_exit_includes_trailing_plan(self):
        plan = plan_exit(symbol="TCS", entry=3500.0, support=3450.0)
        self.assertIn("trailing_plan", plan)
        tp = plan["trailing_plan"]
        self.assertEqual(tp["stage_1_initial_stop"], 3450.0)
        self.assertEqual(tp["stage_2_breakeven_trigger"], 3550.0)  # +1R = +50
        self.assertEqual(tp["stage_3_atr_trail_trigger"], 3600.0)   # +2R = +100
        self.assertEqual(tp["stage_4_structure_trigger"], 3650.0)   # +3R = +150


if __name__ == "__main__":
    unittest.main()
