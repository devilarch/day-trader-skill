#!/usr/bin/env python3
"""Indian Market Entry Timing & Bar Watcher for trader-entry. Standard library only.

Watches Indian market 5-minute bars (09:15 to 15:30 IST):
  - 15-minute Opening Range: 09:15, 09:20, and 09:25 bars.
  - Breakout Signal: First 5-minute candle to CLOSE above the opening range high.
  - Entry Window: Active between 09:30 IST and 15:00 IST.
"""

import argparse
import datetime
import json
import os
import sys
import urllib.request
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from market_calendar_indian import to_ist, is_market_open

def fetch_5m_bars(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=5m"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = data["chart"]["result"][0]
            timestamps = res.get("timestamp", [])
            quotes = res["indicators"]["quote"][0]
            bars = []
            for t, o, h, l, c, v in zip(timestamps, quotes.get("open", []), quotes.get("high", []),
                                       quotes.get("low", []), quotes.get("close", []), quotes.get("volume", [])):
                if None not in (o, h, l, c):
                    dt = datetime.datetime.utcfromtimestamp(t) + datetime.timedelta(hours=5, minutes=30)
                    bars.append({
                        "time": dt.strftime("%H:%M"),
                        "open": o, "high": h, "low": l, "close": c, "volume": v or 0
                    })
            return bars
    except Exception as e:
        return []

def evaluate_orb_entry(symbol):
    now_ist = to_ist()
    mkt_open, msg = is_market_open(now_ist)
    if not mkt_open:
        return {"status": "MARKET_CLOSED", "reason": msg}

    bars = fetch_5m_bars(symbol)
    if len(bars) < 3:
        return {"status": "WAITING", "reason": "Opening range (09:15-09:30 IST) is still forming."}

    # Range bars: first 3 bars (09:15, 09:20, 09:25)
    range_bars = bars[:3]
    or_high = max(b["high"] for b in range_bars)
    or_low = min(b["low"] for b in range_bars)

    # Check breakout in subsequent bars
    for bar in bars[3:]:
        if bar["close"] > or_high:
            return {
                "status": "TRIGGERED",
                "setup": "ORB Breakout",
                "bar_time": bar["time"],
                "trigger_price": bar["close"],
                "or_high": or_high,
                "or_low": or_low,
                "reason": f"Bar at {bar['time']} closed @ ₹{bar['close']:,.2f} above range high ₹{or_high:,.2f}"
            }

    last_close = bars[-1]["close"]
    return {
        "status": "WAITING",
        "or_high": or_high,
        "or_low": or_low,
        "last_price": last_close,
        "reason": f"Trading inside range ({or_low:,.2f} - {or_high:,.2f}). Current: ₹{last_close:,.2f}"
    }

def compute_simple_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas[:period]]
    losses = [abs(min(d, 0)) for d in deltas[:period]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for d in deltas[period:]:
        avg_gain = (avg_gain * (period - 1) + max(d, 0)) / period
        avg_loss = (avg_loss * (period - 1) + abs(min(d, 0))) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def evaluate_3screen_confluence(symbol: str, weekly_candles: list, daily_candles: list, intraday_bars: list = None, support: float = None, resistance: float = None):
    """
    Evaluates Elder's 3-Screen Multi-Timeframe Confluence across 6 factors:
      1. Weekly trend direction agrees (+1)
      2. Daily shows valid setup pattern (+1)
      3. Daily RSI supports (+1)
      4. Daily moving averages support (+1)
      5. Key S/R level provides clear stop and target (+1)
      6. Volume confirms move (+1)

    Scores:
      5-6: Strong setup (Full position size)
      4: Good setup (Full position size)
      3: Marginal setup (Half position size)
      0-2: Weak setup (Skip trade)
    """
    factors = []
    score = 0

    # Factor 1: Weekly Trend Direction (Screen 1)
    weekly_closes = [c["close"] for c in weekly_candles if "close" in c and c["close"] is not None]
    if len(weekly_closes) >= 5:
        w_curr = weekly_closes[-1]
        w_sma20 = sum(weekly_closes[-20:]) / min(len(weekly_closes), 20)
        w_rsi = compute_simple_rsi(weekly_closes)
        if w_curr >= w_sma20 or w_rsi >= 50.0:
            score += 1
            factors.append({"factor": "weekly_trend_agrees", "points": 1, "detail": f"Weekly close ₹{w_curr:,.2f} >= 20W SMA (₹{w_sma20:,.2f}) or Weekly RSI {w_rsi} >= 50"})
        else:
            factors.append({"factor": "weekly_trend_agrees", "points": 0, "detail": f"Weekly close below 20W SMA (Weekly RSI {w_rsi})"})
    else:
        factors.append({"factor": "weekly_trend_agrees", "points": 0, "detail": "Insufficient weekly data"})

    # Factor 2: Daily Setup Pattern (Screen 2)
    daily_closes = [c["close"] for c in daily_candles if "close" in c and c["close"] is not None]
    if len(daily_closes) >= 10:
        d_last = daily_closes[-1]
        d_prev = daily_closes[-2]
        d_sma20 = sum(daily_closes[-20:]) / min(len(daily_closes), 20)
        if d_last >= d_prev or d_last >= d_sma20:
            score += 1
            factors.append({"factor": "daily_setup_valid", "points": 1, "detail": "Daily price action forming valid continuation/breakout setup"})
        else:
            factors.append({"factor": "daily_setup_valid", "points": 0, "detail": "No clear daily setup pattern"})
    else:
        factors.append({"factor": "daily_setup_valid", "points": 0, "detail": "Insufficient daily data"})

    # Factor 3: Daily RSI Supports
    if len(daily_closes) >= 15:
        d_rsi = compute_simple_rsi(daily_closes)
        d_rsi_prev = compute_simple_rsi(daily_closes[:-1])
        if d_rsi >= 50.0 or (d_rsi > d_rsi_prev and d_rsi >= 30.0):
            score += 1
            factors.append({"factor": "daily_rsi_confirms", "points": 1, "detail": f"Daily RSI is {d_rsi} (bullish support zone)"})
        else:
            factors.append({"factor": "daily_rsi_confirms", "points": 0, "detail": f"Daily RSI is {d_rsi} (bearish/lagging)"})
    else:
        factors.append({"factor": "daily_rsi_confirms", "points": 0, "detail": "Insufficient daily data for RSI"})

    # Factor 4: Daily Moving Average Alignment
    if len(daily_closes) >= 20:
        d_sma20 = sum(daily_closes[-20:]) / 20.0
        d_sma50 = sum(daily_closes[-50:]) / min(len(daily_closes), 50)
        if daily_closes[-1] >= d_sma20 or d_sma20 >= d_sma50:
            score += 1
            factors.append({"factor": "daily_ma_alignment", "points": 1, "detail": f"Price ₹{daily_closes[-1]:,.2f} >= SMA20 (₹{d_sma20:,.2f})"})
        else:
            factors.append({"factor": "daily_ma_alignment", "points": 0, "detail": "Price below key moving averages"})
    else:
        factors.append({"factor": "daily_ma_alignment", "points": 0, "detail": "Insufficient daily data for MA"})

    # Factor 5: Key S/R Anchor (Screen 3)
    if daily_closes and support is not None and resistance is not None and support < daily_closes[-1] < resistance:
        score += 1
        factors.append({"factor": "clear_sr_anchor", "points": 1, "detail": f"Clear support (₹{support:,.2f}) and resistance (₹{resistance:,.2f})"})
    elif daily_closes and support is not None and support < daily_closes[-1]:
        score += 1
        factors.append({"factor": "clear_sr_anchor", "points": 1, "detail": f"Clear stop anchor at support (₹{support:,.2f})"})
    else:
        factors.append({"factor": "clear_sr_anchor", "points": 0, "detail": "No verified S/R level provided"})

    # Factor 6: Volume Confirmation
    daily_volumes = [c.get("volume", 0) for c in daily_candles if c.get("volume") is not None]
    if len(daily_volumes) >= 20:
        d_avg_vol = sum(daily_volumes[-20:]) / 20.0
        curr_vol = daily_volumes[-1]
        ratio = curr_vol / d_avg_vol if d_avg_vol > 0 else 1.0
        if ratio >= 1.4:
            score += 1
            factors.append({"factor": "volume_confirmation", "points": 1, "detail": f"Volume ratio {round(ratio, 2)}x >= 1.4x 20-DMA"})
        else:
            factors.append({"factor": "volume_confirmation", "points": 0, "detail": f"Volume ratio {round(ratio, 2)}x < 1.4x 20-DMA"})
    else:
        factors.append({"factor": "volume_confirmation", "points": 0, "detail": "Insufficient volume history"})

    # Verdict & Multiplier
    if score >= 5:
        rating = "STRONG_CONFLUENCE"
        recom = "FULL_POSITION"
        size_mult = 1.0
    elif score == 4:
        rating = "GOOD_CONFLUENCE"
        recom = "FULL_POSITION"
        size_mult = 1.0
    elif score == 3:
        rating = "MARGINAL_CONFLUENCE"
        recom = "HALF_POSITION"
        size_mult = 0.5
    else:
        rating = "WEAK_NO_TRADE"
        recom = "SKIP"
        size_mult = 0.0

    return {
        "symbol": symbol,
        "confluence_score": score,
        "max_score": 6,
        "rating": rating,
        "recommendation": recom,
        "position_size_multiplier": size_mult,
        "factors": factors
    }


def fetch_historical_candles(symbol: str, range_str: str = "1y", interval: str = "1d"):
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
            candles = []
            for o, h, l, c, v in zip(quotes.get("open", []), quotes.get("high", []), quotes.get("low", []), quotes.get("close", []), quotes.get("volume", [])):
                if None not in (o, h, l, c):
                    candles.append({"open": round(o, 2), "high": round(h, 2), "low": round(l, 2), "close": round(c, 2), "volume": v or 0})
            return candles
    except Exception:
        return []


def main():
    parser = argparse.ArgumentParser(description="Indian Market Intraday Entry & 3-Screen Confluence Watcher")
    parser.add_argument("symbol", default="^NSEI", nargs="?", help="Symbol to check (default: ^NSEI)")
    parser.add_argument("--confluence", action="store_true", help="Run 3-Screen Multi-Timeframe Confluence evaluation")
    parser.add_argument("--support", type=float, help="Validated key support price (₹)")
    parser.add_argument("--resistance", type=float, help="Validated key resistance price (₹)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.confluence:
        weekly = fetch_historical_candles(args.symbol, range_str="2y", interval="1wk")
        daily = fetch_historical_candles(args.symbol, range_str="6mo", interval="1d")
        res = evaluate_3screen_confluence(
            symbol=args.symbol,
            weekly_candles=weekly,
            daily_candles=daily,
            support=args.support,
            resistance=args.resistance
        )
        if args.json:
            print(json.dumps(res, indent=2))
            return

        print("=" * 60)
        print(f"🎯 3-SCREEN MULTI-TIMEFRAME CONFLUENCE: {res['symbol']}")
        print("=" * 60)
        print(f"Confluence Score:     {res['confluence_score']}/{res['max_score']}")
        print(f"Rating:               {res['rating']}")
        print(f"Recommendation:       {res['recommendation']} (Multiplier: {res['position_size_multiplier']}x)")
        print("\nFactors Breakdown:")
        for f in res["factors"]:
            badge = "✅" if f["points"] == 1 else "❌"
            print(f"  {badge} {f['factor']:24}: {f['detail']}")
        return

    res = evaluate_orb_entry(args.symbol)

    print("=" * 60)
    print(f"⏱️ INDIAN MARKET ENTRY MONITOR: {args.symbol}")
    print("=" * 60)
    print(f"Status: {res['status']}")
    print(f"Reason: {res['reason']}")
    if "or_high" in res:
        print(f"15m Opening Range: ₹{res['or_low']:,.2f} - ₹{res['or_high']:,.2f}")

if __name__ == "__main__":
    main()
