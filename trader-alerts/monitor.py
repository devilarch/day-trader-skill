#!/usr/bin/env python3
"""Automated 1-Minute Trade Position Monitor & Signal Generator. Standard library only.

Monitors all open positions from trader/portfolio.json (1 stock or multiple stocks).
Fetches live tick & candle data, tracks targets, and generates actionable HOLD/SELL verdicts.
If all positions are closed, outputs STATUS: ALL_CLOSED so the cron job can auto-terminate.
"""

import datetime
import json
import os
import sys
import urllib.request
import zoneinfo

PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "portfolio.json")
ORDERS_FILE = os.path.join(os.path.dirname(__file__), "orders.json")


def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def fetch_quote(ticker):
    """Fetches live 1m market data from Yahoo Finance."""
    sym = ticker.upper()
    if not sym.endswith(".NS") and not sym.endswith(".BO") and not sym.startswith("^"):
        yahoo_sym = f"{sym}.NS"
    else:
        yahoo_sym = sym

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}?interval=1m&range=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            meta = data["chart"]["result"][0]["meta"]
            res = data["chart"]["result"][0]
            ts = res["timestamp"]
            quotes = res["indicators"]["quote"][0]
            valid_bars = [
                (t, o, h, l, c, v)
                for t, o, h, l, c, v in zip(ts, quotes["open"], quotes["high"], quotes["low"], quotes["close"], quotes["volume"])
                if c is not None
            ]
            return {
                "ticker": ticker,
                "price": float(meta.get("regularMarketPrice", 0.0)),
                "high": float(meta.get("regularMarketDayHigh", 0.0)),
                "low": float(meta.get("regularMarketDayLow", 0.0)),
                "prev_close": float(meta.get("previousClose") or meta.get("chartPreviousClose") or 0.0),
                "bars": valid_bars[-5:],
            }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def analyze_position(pos, plan, quote):
    ticker = pos.get("ticker")
    shares = float(pos.get("shares", 0.0))
    if shares <= 0:
        return None

    cost = 0.0
    lots = pos.get("lots", [])
    if lots:
        total_lot_cost = sum(lot.get("cost", 0.0) for lot in lots)
        cost = total_lot_cost / shares if shares > 0 else 0.0
    else:
        cost = float(plan.get("entry") or plan.get("limit_price") or plan.get("price") or 0.0)

    ltp = quote.get("price", 0.0)
    day_high = quote.get("high", 0.0)
    day_low = quote.get("low", 0.0)
    bars = quote.get("bars", [])

    entry = float((plan.get("plan") or {}).get("entry") or cost)
    t1 = float((plan.get("plan") or {}).get("target_1") or plan.get("take_profit_1") or (entry * 1.0075))
    t2 = float((plan.get("plan") or {}).get("target") or plan.get("take_profit_limit_price") or (entry * 1.015))
    sl = float((plan.get("plan") or {}).get("stop") or plan.get("stop_loss_stop_price") or (entry * 0.992))

    unrealized_pnl = round(shares * (ltp - entry), 2)
    pnl_pct = round(((ltp - entry) / entry * 100), 2) if entry > 0 else 0.0

    # Candle momentum analysis
    reasons = []
    verdict = "HOLD"

    if len(bars) >= 2:
        last_close = bars[-1][4]
        prev_close = bars[-2][4]
        last_vol = bars[-1][5] or 0
        prev_vol = bars[-2][5] or 0

        # Check Target 2
        if ltp >= t2 or (day_high >= t2 and ltp >= t2 * 0.998):
            verdict = "SELL / TAKE FULL PROFIT"
            reasons.append(f"Target 2 (₹{t2:.2f}) reached/tested (Current LTP: ₹{ltp:.2f}).")
            reasons.append("Daily 1–2% goal accomplished — lock in full gains now.")

        # Check Target 1
        elif ltp >= t1 or (day_high >= t1 and ltp >= t1 * 0.998):
            verdict = "PARTIAL SELL / TRAIL SL"
            reasons.append(f"Target 1 (₹{t1:.2f}) touched (High: ₹{day_high:.2f}).")
            reasons.append(f"Recommended: De-risk 50–70% of position and trail SL to cost (₹{entry:.2f}).")

        # Check Stop Loss
        elif ltp <= sl:
            verdict = "STOP OUT"
            reasons.append(f"LTP (₹{ltp:.2f}) breached Stop-Loss level (₹{sl:.2f}).")
            reasons.append("Exit position immediately to protect capital.")

        # Check Momentum rollover
        elif last_close < prev_close and last_vol > prev_vol * 1.5 and pnl_pct > 0.5:
            verdict = "CONSIDER EXITING"
            reasons.append(f"Volume selling wick detected on 1m chart (Vol: {last_vol:,}).")
            reasons.append(f"Price rejected from ₹{day_high:.2f}; protect current +₹{unrealized_pnl:.2f} profit.")

        # Bullish hold
        else:
            verdict = "HOLD"
            if last_close >= prev_close:
                reasons.append("1-minute candle structure making higher lows.")
            else:
                reasons.append(f"Holding constructive base above support (Low: ₹{day_low:.2f}).")
            reasons.append(f"Trending toward T1: ₹{t1:.2f} / T2: ₹{t2:.2f}. Downside capped at SL: ₹{sl:.2f}.")

    return {
        "ticker": ticker,
        "shares": shares,
        "entry": entry,
        "ltp": ltp,
        "day_high": day_high,
        "day_low": day_low,
        "unrealized_pnl": unrealized_pnl,
        "pnl_pct": pnl_pct,
        "t1": t1,
        "t2": t2,
        "sl": sl,
        "verdict": verdict,
        "reasons": reasons,
    }


def main():
    portfolio = load_json(PORTFOLIO_FILE) or {}
    positions = portfolio.get("positions", [])
    active_positions = [p for p in positions if float(p.get("shares", 0.0)) > 0]

    if not active_positions:
        print("STATUS: ALL_CLOSED")
        print("All trading positions are completely closed (0 open shares).")
        print("ACTION_REQUIRED: Stop recurring cron monitor job.")
        sys.exit(0)

    orders_data = load_json(ORDERS_FILE) or []
    plan_map = {}
    if isinstance(orders_data, list):
        for o in orders_data:
            sym = (o.get("tradingsymbol") or o.get("symbol") or "").replace("NSE:", "").replace(".NS", "")
            if sym:
                plan_map[sym] = o

    now_ist = datetime.datetime.now(zoneinfo.ZoneInfo("Asia/Kolkata"))
    print("=" * 65)
    print(f"📊 LIVE POSITION MONITOR ({now_ist.strftime('%H:%M:%S')} IST)")
    print(f"Active Positions: {len(active_positions)}")
    print("=" * 65)

    for pos in active_positions:
        ticker = pos.get("ticker", "").replace("NSE:", "").replace(".NS", "")
        plan = plan_map.get(ticker, {})
        quote = fetch_quote(ticker)

        if "error" in quote:
            print(f"⚠️ Error fetching quote for {ticker}: {quote['error']}")
            continue

        res = analyze_position(pos, plan, quote)
        if not res:
            continue

        sign = "+" if res["unrealized_pnl"] >= 0 else ""
        print(f"\n🏷️  {res['ticker']} | {int(res['shares'])} shares @ ₹{res['entry']:.2f}")
        print(f"   LTP: ₹{res['ltp']:.2f} (Day High: ₹{res['day_high']:.2f})")
        print(f"   Unrealized PnL: {sign}₹{res['unrealized_pnl']:.2f} ({sign}{res['pnl_pct']:.2f}%)")
        print(f"   Targets: T1=₹{res['t1']:.2f} | T2=₹{res['t2']:.2f} | SL=₹{res['sl']:.2f}")
        print(f"   ▶ VERDICT: 【 {res['verdict']} 】")
        for r in res["reasons"]:
            print(f"     • {r}")

    print("\n" + "=" * 65)


if __name__ == "__main__":
    main()
