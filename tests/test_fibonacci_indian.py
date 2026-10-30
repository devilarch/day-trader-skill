#!/usr/bin/env python3
"""Unit tests for Indian Market Fibonacci Retracement & Extension Engine (trader-exit/exit_indian.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "trader-exit")))
from exit_indian import calculate_fibonacci_levels, plan_exit


class TestFibonacciIndian(unittest.TestCase):
    def test_fibonacci_retracements(self):
        # Swing high = 2000, Swing low = 1000 (diff = 1000)
        fib = calculate_fibonacci_levels(swing_high=2000.0, swing_low=1000.0)
        retrace = fib["retracements"]
        self.assertEqual(retrace["23.6%"], 1764.0)
        self.assertEqual(retrace["38.2%"], 1618.0)
        self.assertEqual(retrace["50.0%"], 1500.0)
        self.assertEqual(retrace["61.8%"], 1382.0)
        self.assertEqual(retrace["78.6%"], 1214.0)

    def test_fibonacci_extensions(self):
        # Diff = 1000, point_c (retracement low) = 1400
        fib = calculate_fibonacci_levels(swing_high=2000.0, swing_low=1000.0, point_c=1400.0)
        ext = fib["extensions"]
        self.assertEqual(ext["100.0%"], 2400.0)
        self.assertEqual(ext["127.2%"], 2672.0)
        self.assertEqual(ext["161.8%"], 3018.0)
        self.assertEqual(ext["200.0%"], 3400.0)

    def test_invalid_swing_levels(self):
        with self.assertRaises(ValueError):
            calculate_fibonacci_levels(swing_high=1000.0, swing_low=1000.0)
        with self.assertRaises(ValueError):
            calculate_fibonacci_levels(swing_high=900.0, swing_low=1000.0)

    def test_plan_exit_integrates_fibonacci(self):
        plan = plan_exit(
            symbol="INFY",
            entry=1500.0,
            fib_high=1600.0,
            fib_low=1400.0,
            fib_c=1450.0
        )
        self.assertIn("fibonacci", plan)
        self.assertEqual(plan["fibonacci"]["retracements"]["50.0%"], 1500.0)
        self.assertEqual(plan["fibonacci"]["extensions"]["127.2%"], 1704.4)


if __name__ == "__main__":
    unittest.main()
