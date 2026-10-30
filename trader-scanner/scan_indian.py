#!/usr/bin/env python3
"""Indian Market Comprehensive Setup & Breakout Scanner for trader-scanner. Standard library only.

Features matching professional scanner standards:
  - Scans Indian liquid universe (NSE 100 + top F&O momentum equities).
  - Daily Setups:
      1. breakout_20d: Last close exceeds 20-day closing high.
      2. bull_flag: Up >10% over prior 10 days, followed by tight 5-day consolidation (<5%).
      3. reclaim_ma20: Closed below 20-DMA then reclaimed above it.
      4. oversold: 14-day RSI < 30.
      5. oversold_bounce: RSI was <30, now turning up with green close.
  - Opening Range Breakout (ORB):
      Detects 5-minute candles closing above the 09:15-09:30 IST opening range high.
  - Writes results directly to trader/watchlist.json for trader-news & trader-entry.
"""

import argparse
import datetime as _dt
import json
import math
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from market_calendar_indian import to_ist, is_market_open

DEFAULT_UNIVERSE_FILE = "trader/universe.txt"
DEFAULT_WATCHLIST_FILE = "trader/watchlist.json"

def load_universe(filepath=DEFAULT_UNIVERSE_FILE):
    if os.path.exists(filepath):
        symbols = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    sym = line.split("|")[0].strip()
                    if sym:
                        symbols.append(sym)
        if symbols:
            return symbols

    # Fallback to universe_indian.py if file not yet generated
    from universe_indian import INDIAN_STOCKS
    return [sym for sym, _ in INDIAN_STOCKS]

def fetch_chart(symbol, range_str="3mo", interval="1d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={range_str}&interval={interval}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = data["chart"]["result"][0]
            quotes = res["indicators"]["quote"][0]
            meta = res["meta"]
            return {
                "symbol": symbol,
                "closes": [c for c in quotes.get("close", []) if c is not None],
                "highs": [h for h in quotes.get("high", []) if h is not None],
                "lows": [l for l in quotes.get("low", []) if l is not None],
                "volumes": [v for v in quotes.get("volume", []) if v is not None],
                "last_price": meta.get("regularMarketPrice") or quotes.get("close", [-1])[-1]
            }
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}

def compute_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas[:period]]
    losses = [abs(min(d, 0)) for d in deltas[:period]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    for d in deltas[period:]:
        gain = max(d, 0)
        loss = abs(min(d, 0))
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def compute_rsi_series(closes, period=14):
    if len(closes) < period + 1:
        return [50.0] * len(closes)
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas[:period]]
    losses = [abs(min(d, 0)) for d in deltas[:period]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    rsis = [50.0] * period
    first_rs = (avg_gain / avg_loss) if avg_loss != 0 else 100.0
    first_rsi = 100.0 if avg_loss == 0 else round(100.0 - (100.0 / (1.0 + first_rs)), 2)
    rsis.append(first_rsi)

    for d in deltas[period:]:
        gain = max(d, 0)
        loss = abs(min(d, 0))
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            rsis.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsis.append(round(100.0 - (100.0 / (1.0 + rs)), 2))
    return rsis


def detect_rsi_divergences(closes: list, rsis: list = None, lookback: int = 30):
    """
    Detects Regular and Hidden RSI divergences across price swing extrema:
      - Regular Bullish: Price Lower Low, RSI Higher Low (reversal)
      - Hidden Bullish: Price Higher Low, RSI Lower Low (trend continuation)
      - Regular Bearish: Price Higher High, RSI Lower High (reversal)
      - Hidden Bearish: Price Lower High, RSI Higher High (trend continuation)
    """
    if len(closes) < 20:
        return []

    if rsis is None or len(rsis) != len(closes):
        rsis = compute_rsi_series(closes)

    c_win = closes[-lookback:]
    r_win = rsis[-lookback:]
    n = len(c_win)

    swing_lows = []
    swing_highs = []
    for i in range(1, n - 1):
        if c_win[i] < c_win[i - 1] and c_win[i] < c_win[i + 1]:
            swing_lows.append((i, c_win[i], r_win[i]))
        if c_win[i] > c_win[i - 1] and c_win[i] > c_win[i + 1]:
            swing_highs.append((i, c_win[i], r_win[i]))

    divergences = []

    # Check Bullish Divergences between the last two swing lows
    if len(swing_lows) >= 2:
        (i1, p1, r1) = swing_lows[-2]
        (i2, p2, r2) = swing_lows[-1]
        # Regular Bullish (Price Lower Low, RSI Higher Low)
        if p2 < p1 and r2 > r1:
            divergences.append({
                "type": "bullish_regular_divergence",
                "swing1": (p1, r1),
                "swing2": (p2, r2),
                "description": f"Regular Bullish Divergence: Price made lower low (₹{p1:,.2f} -> ₹{p2:,.2f}) while RSI made higher low ({r1} -> {r2})"
            })
        # Hidden Bullish (Price Higher Low, RSI Lower Low)
        elif p2 > p1 and r2 < r1:
            divergences.append({
                "type": "bullish_hidden_divergence",
                "swing1": (p1, r1),
                "swing2": (p2, r2),
                "description": f"Hidden Bullish Divergence: Price made higher low (₹{p1:,.2f} -> ₹{p2:,.2f}) while RSI made lower low ({r1} -> {r2})"
            })

    # Check Bearish Divergences between the last two swing highs
    if len(swing_highs) >= 2:
        (i1, p1, r1) = swing_highs[-2]
        (i2, p2, r2) = swing_highs[-1]
        # Regular Bearish (Price Higher High, RSI Lower High)
        if p2 > p1 and r2 < r1:
            divergences.append({
                "type": "bearish_regular_divergence",
                "swing1": (p1, r1),
                "swing2": (p2, r2),
                "description": f"Regular Bearish Divergence: Price made higher high (₹{p1:,.2f} -> ₹{p2:,.2f}) while RSI made lower high ({r1} -> {r2})"
            })
        # Hidden Bearish (Price Lower High, RSI Higher High)
        elif p2 < p1 and r2 > r1:
            divergences.append({
                "type": "bearish_hidden_divergence",
                "swing1": (p1, r1),
                "swing2": (p2, r2),
                "description": f"Hidden Bearish Divergence: Price made lower high (₹{p1:,.2f} -> ₹{p2:,.2f}) while RSI made higher high ({r1} -> {r2})"
            })

    return divergences

def scan_daily_setups(symbols, min_price=50.0, limit=None):
    hits = []
    print(f"🔍 Scanning {len(symbols)} Indian symbols for daily setups...")
    scanned_count = 0

    for sym in symbols:
        if limit and scanned_count >= limit:
            break
        scanned_count += 1
        data = fetch_chart(sym, range_str="3mo", interval="1d")
        if "error" in data or len(data.get("closes", [])) < 22:
            continue

        closes = data["closes"]
        last = closes[-1]
        prev = closes[-2]
        if last < min_price:
            continue

        prev_20 = closes[-21:-1]
        # 1. 20-Day Closing High Breakout
        if last > max(prev_20):
            pct_over = round(((last - max(prev_20)) / max(prev_20)) * 100, 2)
            hits.append({"symbol": sym, "setup": "breakout_20d", "price": last, "detail": f"+{pct_over}% above 20D high"})
            continue

        # 2. Bull Flag: Up >10% over sessions -15 to -5, then last 5 consolidate within 5% band
        if len(closes) >= 16:
            pole_start = closes[-15]
            pole_peak = max(closes[-15:-5])
            pole_gain = (pole_peak - pole_start) / pole_start
            flag_range = (max(closes[-5:]) - min(closes[-5:])) / min(closes[-5:])
            if pole_gain >= 0.10 and flag_range <= 0.05 and last >= closes[-5]:
                hits.append({"symbol": sym, "setup": "bull_flag", "price": last, "detail": f"Pole +{round(pole_gain*100,1)}%, flag {round(flag_range*100,1)}%"})
                continue

        # 3. 20-Day Moving Average Reclaim
        ma20 = sum(prev_20) / len(prev_20)
        if prev < ma20 and last > ma20:
            hits.append({"symbol": sym, "setup": "reclaim_ma20", "price": last, "detail": f"Crossed above 20-DMA (₹{round(ma20,2)})"})
            continue

        # 4 & 5. RSI Oversold and Oversold Bounce
        rsi_now = compute_rsi(closes, period=14)
        rsi_prev = compute_rsi(closes[:-1], period=14)
        if rsi_now and rsi_now < 30.0:
            hits.append({"symbol": sym, "setup": "oversold", "price": last, "detail": f"RSI 14 = {rsi_now}"})
            continue
        elif rsi_prev and rsi_prev < 30.0 and last > prev and rsi_now > rsi_prev:
            hits.append({"symbol": sym, "setup": "oversold_bounce", "price": last, "detail": f"Rebounded from RSI {rsi_prev} to {rsi_now}"})
            continue

        # 6. RSI Divergences (Regular & Hidden)
        divs = detect_rsi_divergences(closes)
        for d in divs:
            if d["type"].startswith("bullish"):
                hits.append({"symbol": sym, "setup": d["type"], "price": last, "detail": d["description"]})
                break

    return hits

def scan_orb_setups(symbols, min_price=50.0):
    hits = []
    print(f"⏱️ Scanning {len(symbols)} Indian symbols for 15m Opening Range Breakouts (ORB)...")
    for sym in symbols:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=1d&interval=5m"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                res = data["chart"]["result"][0]
                quotes = res["indicators"]["quote"][0]
                timestamps = res.get("timestamp", [])
                bars = []
                for t, o, h, l, c, v in zip(timestamps, quotes.get("open", []), quotes.get("high", []),
                                           quotes.get("low", []), quotes.get("close", []), quotes.get("volume", [])):
                    if None not in (o, h, l, c):
                        dt = _dt.datetime.utcfromtimestamp(t) + _dt.timedelta(hours=5, minutes=30)
                        bars.append({"time": dt.strftime("%H:%M"), "open": o, "high": h, "low": l, "close": c, "volume": v or 0})

                if len(bars) < 4:
                    continue
                # Opening 15m range (09:15, 09:20, 09:25)
                or_bars = bars[:3]
                or_high = max(b["high"] for b in or_bars)
                or_low = min(b["low"] for b in or_bars)
                avg_or_vol = sum(b["volume"] for b in or_bars) / len(or_bars) if or_bars else 1

                for b in bars[3:]:
                    if b["close"] > or_high:
                        vol_ratio = round(b["volume"] / avg_or_vol, 2) if avg_or_vol else 1.0
                        hits.append({
                            "symbol": sym,
                            "setup": "orb_breakout",
                            "price": b["close"],
                            "or_high": or_high,
                            "or_low": or_low,
                            "breakout_time": b["time"],
                            "volume_ratio": vol_ratio,
                            "detail": f"Closed @ ₹{b['close']:,.2f} above range high ₹{or_high:,.2f} ({b['time']} IST)"
                        })
                        break
        except Exception:
            continue
    return hits

def main():
    parser = argparse.ArgumentParser(description="Indian Market Scanner (Daily & ORB)")
    parser.add_argument("command", choices=["daily", "orb", "universe"], default="daily", nargs="?",
                        help="Scan mode: daily setups, orb (opening range), or universe")
    parser.add_argument("--symbols", nargs="+", help="Specific symbols to scan")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of symbols to scan")
    parser.add_argument("--min-price", type=float, default=50.0, help="Minimum stock price in ₹")
    parser.add_argument("--write", action="store_true", default=True, help="Write hits to trader/watchlist.json")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.command == "universe":
        from universe_indian import build_universe
        build_universe(DEFAULT_UNIVERSE_FILE)
        return

    symbols = args.symbols or load_universe(DEFAULT_UNIVERSE_FILE)

    if args.command == "daily":
        hits = scan_daily_setups(symbols, min_price=args.min_price, limit=args.limit)
    else:
        hits = scan_orb_setups(symbols, min_price=args.min_price)

    if args.write:
        os.makedirs(os.path.dirname(DEFAULT_WATCHLIST_FILE), exist_ok=True)
        watchlist_payload = {
            "date": _dt.datetime.now().strftime("%Y-%m-%d"),
            "scan_mode": args.command,
            "count": len(hits),
            "hits": hits
        }
        with open(DEFAULT_WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(watchlist_payload, f, indent=2)

    if args.json:
        print(json.dumps(hits, indent=2))
        return

    print("=" * 75)
    print(f"🎯 INDIAN MARKET {args.command.upper()} SETUPS SCAN ({len(hits)} Hits Found)")
    print("=" * 75)
    if not hits:
        print("No setups meeting criteria found in the scanned universe.")
        return

    for h in hits:
        sym_clean = h['symbol'].replace(".NS", "")
        print(f"🔥 {sym_clean:<12} | {h['setup']:<16} | Price: ₹{h['price']:<9,.2f} | {h['detail']}")

if __name__ == "__main__":
    main()
