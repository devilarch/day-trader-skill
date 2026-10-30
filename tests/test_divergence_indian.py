#!/usr/bin/env python3
"""Unit tests for Indian Market Regular & Hidden RSI Divergence Engine (trader-scanner/scan_indian.py)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "trader-scanner")))
from scan_indian import detect_rsi_divergences


class TestRsiDivergenceIndian(unittest.TestCase):
    def test_regular_bullish_divergence(self):
        # 30 price and rsi points
        # Swing Low 1 at index 10: price 100.0, rsi 25.0
        # Swing Low 2 at index 25: price 90.0 (Lower Low), rsi 32.0 (Higher Low)
        closes = [110.0] * 30
        rsis = [50.0] * 30

        # Create swing 1
        closes[9], closes[10], closes[11] = 105.0, 100.0, 104.0
        rsis[9], rsis[10], rsis[11] = 30.0, 25.0, 32.0

        # Create swing 2 (lower low price, higher low rsi)
        closes[24], closes[25], closes[26] = 95.0, 90.0, 96.0
        rsis[24], rsis[25], rsis[26] = 35.0, 32.0, 38.0

        divs = detect_rsi_divergences(closes, rsis=rsis)
        types = [d["type"] for d in divs]
        self.assertIn("bullish_regular_divergence", types)

    def test_hidden_bullish_divergence(self):
        # Hidden bullish: Price Higher Low, RSI Lower Low
        closes = [110.0] * 30
        rsis = [50.0] * 30

        # Swing 1: price 90, rsi 38
        closes[9], closes[10], closes[11] = 96.0, 90.0, 95.0
        rsis[9], rsis[10], rsis[11] = 42.0, 38.0, 44.0

        # Swing 2: price 96 (Higher Low), rsi 30 (Lower Low)
        closes[24], closes[25], closes[26] = 100.0, 96.0, 101.0
        rsis[24], rsis[25], rsis[26] = 36.0, 30.0, 37.0

        divs = detect_rsi_divergences(closes, rsis=rsis)
        types = [d["type"] for d in divs]
        self.assertIn("bullish_hidden_divergence", types)

    def test_regular_bearish_divergence(self):
        # Regular bearish: Price Higher High, RSI Lower High
        closes = [110.0] * 30
        rsis = [50.0] * 30

        # Swing 1: price 150, rsi 75
        closes[9], closes[10], closes[11] = 145.0, 150.0, 146.0
        rsis[9], rsis[10], rsis[11] = 70.0, 75.0, 68.0

        # Swing 2: price 160 (Higher High), rsi 68 (Lower High)
        closes[24], closes[25], closes[26] = 155.0, 160.0, 154.0
        rsis[24], rsis[25], rsis[26] = 64.0, 68.0, 63.0

        divs = detect_rsi_divergences(closes, rsis=rsis)
        types = [d["type"] for d in divs]
        self.assertIn("bearish_regular_divergence", types)

    def test_insufficient_data(self):
        divs = detect_rsi_divergences([100.0, 101.0, 102.0])
        self.assertEqual(divs, [])


if __name__ == "__main__":
    unittest.main()
