#!/usr/bin/env python3
"""Indian Market Technical S/R & Volume Analysis Engine for trader-analyst. Standard library only.

Provides systematic chart reading for Indian NSE/BSE equities:
1. Horizontal Support & Resistance mapping with multi-touch confirmation (>= 2 touches).
2. Volume confirmation matrix (>1.5x 20-DMA volume expansion vs exhaustion rally).
3. Moving Average alignment (SMA20, SMA50, SMA200).
4. 3-Scenario probabilistic projection (Bullish / Bearish / Rangebound summing to 100%).
"""

import argparse
import datetime
import json
import math
import os
import sys
import urllib.request


def identify_sr_levels(candles: list, current_price: float, min_touches: int = 2, tolerance_pct: float = 0.0075):
    """
    Identifies horizontal support and resistance levels from candle history:
      - Groups swing extrema within tolerance_pct.
      - Requires >= min_touches for validation.
      - Finds nearest verified support and resistance around current_price.
    """
    if not candles:
        return {"nearest_support": None, "nearest_resistance": None, "levels": []}

    highs = [c["high"] for c in candles if "high" in c and c["high"] is not None]
    lows = [c["low"] for c in candles if "low" in c and c["low"] is not None]
    closes = [c["close"] for c in candles if "close" in c and c["close"] is not None]

    # Extract swing highs and swing lows (local extrema)
    swing_highs = []
    swing_lows = []
    n = len(candles)
    for i in range(1, n - 1):
        h_prev, h_curr, h_next = candles[i-1].get("high"), candles[i].get("high"), candles[i+1].get("high")
        l_prev, l_curr, l_next = candles[i-1].get("low"), candles[i].get("low"), candles[i+1].get("low")
        if None not in (h_prev, h_curr, h_next) and h_curr > h_prev and h_curr > h_next:
            swing_highs.append(h_curr)
        if None not in (l_prev, l_curr, l_next) and l_curr < l_prev and l_curr < l_next:
            swing_lows.append(l_curr)

    points_high = swing_highs if len(swing_highs) >= min_touches else highs
    points_low = swing_lows if len(swing_lows) >= min_touches else lows

    # Cluster price points to find S/R levels
    def cluster_points(points):
        clusters = []
        for p in points:
            matched = False
            for c in clusters:
                avg = sum(c) / len(c)
                if abs(p - avg) / avg <= tolerance_pct:
                    c.append(p)
                    matched = True
                    break
            if not matched:
                clusters.append([p])
        return [
            {"price": round(sum(c) / len(c), 2), "touches": len(c)}
            for c in clusters if len(c) >= min_touches
        ]

    resistance_levels = sorted(cluster_points(points_high), key=lambda x: x["price"])
    support_levels = sorted(cluster_points(points_low), key=lambda x: x["price"])

    # Find nearest resistance above current price
    resistances_above = [r for r in resistance_levels if r["price"] > current_price]
    nearest_res = min(resistances_above, key=lambda x: x["price"]) if resistances_above else None

    # Find nearest support below current price
    supports_below = [s for s in support_levels if s["price"] < current_price]
    nearest_sup = max(supports_below, key=lambda x: x["price"]) if supports_below else None

    # Dynamic Moving Averages
    ma20 = round(sum(closes[-20:]) / len(closes[-20:]), 2) if len(closes) >= 20 else None
    ma50 = round(sum(closes[-50:]) / len(closes[-50:]), 2) if len(closes) >= 50 else None
    ma200 = round(sum(closes[-200:]) / len(closes[-200:]), 2) if len(closes) >= 200 else None

    # Psychological round numbers
    round_step = 50.0 if current_price < 1000 else 100.0 if current_price < 2500 else 500.0
    psych_below = round(math.floor(current_price / round_step) * round_step, 2)
    psych_above = round(math.ceil(current_price / round_step) * round_step, 2)

    return {
        "current_price": current_price,
        "nearest_support": nearest_sup or {"price": psych_below, "touches": 1, "type": "psychological"},
        "nearest_resistance": nearest_res or {"price": psych_above, "touches": 1, "type": "psychological"},
        "all_supports": [s for s in support_levels if s["price"] <= current_price],
        "all_resistances": [r for r in resistance_levels if r["price"] >= current_price],
        "moving_averages": {
            "sma20": ma20,
            "sma50": ma50,
            "sma200": ma200
        },
        "psychological_levels": {
            "lower_round": psych_below,
            "upper_round": psych_above
        }
    }


def analyze_volume(candles: list, current_volume: float = None, price_change_pct: float = 0.0, avg_period: int = 20):
    """
    Analyzes volume vs 20-DMA volume and classifies price/volume confluence:
      - Confirmed Breakout: Rising price + Volume > 1.5x average.
      - Exhaustion Rally: Rising price + Volume < 0.8x average.
      - Heavy Distribution: Falling price + Volume > 1.5x average.
      - Selling Exhaustion: Falling price + Volume < 0.8x average.
    """
    volumes = [c.get("volume", 0) for c in candles if c.get("volume") is not None]
    if len(volumes) >= avg_period:
        avg_volume = sum(volumes[-avg_period:]) / avg_period
    elif volumes:
        avg_volume = sum(volumes) / len(volumes)
    else:
        avg_volume = 1.0

    curr_vol = current_volume if current_volume is not None else (volumes[-1] if volumes else 1.0)
    ratio = round(curr_vol / avg_volume, 2) if avg_volume > 0 else 1.0

    if ratio >= 1.5 and price_change_pct >= 0:
        status = "CONFIRMED_EXPANSION"
        is_confirmed = True
        interp = f"Strong volume surge ({ratio}x > 1.5x 20-DMA). Healthy buying conviction."
    elif ratio < 0.8 and price_change_pct > 0:
        status = "EXHAUSTION_RALLY"
        is_confirmed = False
        interp = f"Low volume advance ({ratio}x < 0.8x 20-DMA). Suspect move with exhaustion risk."
    elif ratio >= 1.5 and price_change_pct < 0:
        status = "HEAVY_DISTRIBUTION"
        is_confirmed = False
        interp = f"Heavy selling volume ({ratio}x > 1.5x 20-DMA). Institutional distribution."
    elif ratio < 0.8 and price_change_pct < 0:
        status = "SELLING_EXHAUSTION"
        is_confirmed = True
        interp = f"Drying up volume on decline ({ratio}x < 0.8x). Potential capitulation/bounce zone."
    else:
        status = "NORMAL_VOLUME"
        is_confirmed = True
        interp = f"Volume within standard bounds ({ratio}x 20-DMA)."

    return {
        "current_volume": curr_vol,
        "avg_20_volume": round(avg_volume, 0),
        "volume_ratio": ratio,
        "status": status,
        "is_confirmed": is_confirmed,
        "interpretation": interp
    }


def generate_technical_assessment(symbol: str, candles: list, current_price: float = None, current_volume: float = None):
    """
    Full technical assessment synthesis: S/R, volume confirmation, moving averages, and probabilistic scenarios.
    """
    if not candles:
        raise ValueError("Candles list cannot be empty")

    curr_p = current_price if current_price is not None else candles[-1]["close"]
    prev_close = candles[-2]["close"] if len(candles) >= 2 else curr_p
    price_change_pct = round(((curr_p - prev_close) / prev_close) * 100.0, 2) if prev_close else 0.0

    sr = identify_sr_levels(candles, current_price=curr_p)
    vol = analyze_volume(candles, current_volume=current_volume, price_change_pct=price_change_pct)

    sup = sr["nearest_support"]["price"]
    res = sr["nearest_resistance"]["price"]

    # Moving average trend determination
    ma = sr["moving_averages"]
    if ma["sma20"] and ma["sma50"] and curr_p > ma["sma20"] > ma["sma50"]:
        trend = "STRONG_UPTREND"
        bullish_prob = 60 if vol["is_confirmed"] else 45
    elif ma["sma20"] and ma["sma50"] and curr_p < ma["sma20"] < ma["sma50"]:
        trend = "STRONG_DOWNTREND"
        bullish_prob = 25
    else:
        trend = "CONSOLIDATION_NEUTRAL"
        bullish_prob = 40

    bearish_prob = 100 - bullish_prob - 20
    sideways_prob = 20

    scenarios = {
        "scenario_a_bullish": {
            "name": "Bullish Continuation / Breakout",
            "probability_pct": bullish_prob,
            "trigger": f"Price holds support @ ₹{sup:,.2f} or breaks resistance @ ₹{res:,.2f} on volume",
            "target": f"₹{res:,.2f} (Immediate Resistance) / Extension",
            "invalidation": f"Sustained close below ₹{sup:,.2f}"
        },
        "scenario_b_bearish": {
            "name": "Bearish Breakdown / Rejection",
            "probability_pct": bearish_prob,
            "trigger": f"Rejection at ₹{res:,.2f} or break below support @ ₹{sup:,.2f}",
            "target": f"₹{sup:,.2f} (Immediate Support)",
            "invalidation": f"Breakout above ₹{res:,.2f}"
        },
        "scenario_c_sideways": {
            "name": "Rangebound Consolidation",
            "probability_pct": sideways_prob,
            "range": f"₹{sup:,.2f} to ₹{res:,.2f}",
            "action": "Avoid mid-range chop; trade only at boundaries"
        }
    }

    return {
        "symbol": symbol,
        "current_price": curr_p,
        "price_change_pct": price_change_pct,
        "trend_state": trend,
        "support_resistance": sr,
        "volume_analysis": vol,
        "scenarios": scenarios
    }


def fetch_yahoo_candles(symbol: str, range_str: str = "3mo", interval: str = "1d"):
    """Fetches online candles from Yahoo Finance with Indian ticker normalization."""
    clean_sym = symbol.strip().upper()
    if not clean_sym.endswith(".NS") and not clean_sym.endswith(".BO") and not clean_sym.startswith("^"):
        clean_sym = f"{clean_sym}.NS"

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{clean_sym}?range={range_str}&interval={interval}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = data["chart"]["result"][0]
            quotes = res["indicators"]["quote"][0]
            timestamps = res.get("timestamp", [])
            candles = []
            for t, o, h, l, c, v in zip(timestamps, quotes.get("open", []), quotes.get("high", []),
                                       quotes.get("low", []), quotes.get("close", []), quotes.get("volume", [])):
                if None not in (o, h, l, c):
                    candles.append({
                        "timestamp": t,
                        "open": round(o, 2),
                        "high": round(h, 2),
                        "low": round(l, 2),
                        "close": round(c, 2),
                        "volume": v or 0
                    })
            return candles
    except Exception as e:
        return []


def main():
    parser = argparse.ArgumentParser(description="Indian Market Technical S/R & Volume Analysis Engine")
    parser.add_argument("symbol", default="RELIANCE", nargs="?", help="Symbol (e.g. RELIANCE, TCS, INFY)")
    parser.add_argument("--candles-file", help="Path to JSON file with candle data")
    parser.add_argument("--current-price", type=float, help="Explicit current price (₹)")
    parser.add_argument("--current-volume", type=float, help="Explicit current volume")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    candles = []
    if args.candles_file and os.path.exists(args.candles_file):
        with open(args.candles_file, "r") as f:
            candles = json.load(f)
    else:
        candles = fetch_yahoo_candles(args.symbol)

    if not candles:
        print(f"Error: Unable to load candle data for {args.symbol}", file=sys.stderr)
        sys.exit(1)

    assessment = generate_technical_assessment(
        symbol=args.symbol,
        candles=candles,
        current_price=args.current_price,
        current_volume=args.current_volume
    )

    if args.json:
        print(json.dumps(assessment, indent=2))
        return

    sr = assessment["support_resistance"]
    vol = assessment["volume_analysis"]
    sc = assessment["scenarios"]

    print("=" * 65)
    print(f"📊 INDIAN MARKET TECHNICAL ANALYSIS: {assessment['symbol']}")
    print("=" * 65)
    print(f"Current Price:        ₹{assessment['current_price']:,.2f} ({assessment['price_change_pct']:+.2f}%)")
    print(f"Trend State:          {assessment['trend_state']}")
    print(f"Nearest Support:      ₹{sr['nearest_support']['price']:,.2f} ({sr['nearest_support'].get('touches', 1)} touches)")
    print(f"Nearest Resistance:   ₹{sr['nearest_resistance']['price']:,.2f} ({sr['nearest_resistance'].get('touches', 1)} touches)")
    if sr['moving_averages']['sma20']:
        print(f"Dynamic MAs:          SMA20: ₹{sr['moving_averages']['sma20']} | SMA50: ₹{sr['moving_averages']['sma50']}")
    print("-" * 65)
    print(f"Volume Confluence:    {vol['status']} (Ratio: {vol['volume_ratio']}x 20-DMA)")
    print(f"Volume Interpretation: {vol['interpretation']}")
    print("-" * 65)
    print("🎯 PROBABILISTIC TRADE SCENARIOS:")
    print(f"  [A] Bullish ({sc['scenario_a_bullish']['probability_pct']}%): {sc['scenario_a_bullish']['trigger']} -> Target {sc['scenario_a_bullish']['target']}")
    print(f"  [B] Bearish ({sc['scenario_b_bearish']['probability_pct']}%): {sc['scenario_b_bearish']['trigger']} -> Target {sc['scenario_b_bearish']['target']}")
    print(f"  [C] Sideways ({sc['scenario_c_sideways']['probability_pct']}%): Range {sc['scenario_c_sideways']['range']}")


if __name__ == "__main__":
    main()
