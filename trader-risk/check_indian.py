#!/usr/bin/env python3
"""Indian Market Risk & Gatekeeper Check for trader-risk. Standard library only.

Checks orders against Indian regulatory and account risk limits:
  1. Market Status: Is NSE/BSE open (09:15 - 15:30 IST) on a non-holiday?
  2. Max Loss: Position loss does not exceed max_loss_per_trade_inr (e.g. ₹2,000).
  3. Daily Loss: Accumulated loss does not exceed max_daily_loss_inr (e.g. ₹5,000).
  4. Max Trades: Does not exceed max_trades_per_day (default 3).
  5. Square-Off Rule: Blocks new intraday entries after 15:00 IST.
  6. Lot Multiples: Ensures quantity is an exact multiple of the index lot.
  7. Expected Value (EV) & Win-Rate R:R Filter: Rejects sub-breakeven R:R or negative EV setups.
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from market_calendar_indian import to_ist, is_market_open, SQUARE_OFF_TIME

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "config_indian.json")


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {
        "max_loss_per_trade_inr": 2000,
        "max_daily_loss_inr": 5000,
        "max_trades_per_day": 3,
        "indices": {"NIFTY": {"lot_size": 25}, "BANKNIFTY": {"lot_size": 15}, "SENSEX": {"lot_size": 10}}
    }


def calculate_expected_value(win_rate: float, avg_win: float, avg_loss: float):
    """
    Computes Expected Value (EV) per trade:
      EV = (Win Rate * Avg Win) - ((1 - Win Rate) * Avg Loss)
    """
    w = max(0.01, min(0.99, win_rate))
    ev = round((w * avg_win) - ((1.0 - w) * avg_loss), 2)
    return {
        "win_rate": w,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "ev": ev,
        "has_positive_edge": ev > 0
    }


def evaluate_rr_and_ev(entry: float, stop: float, target_1: float, target_2: float = None, win_rate: float = 0.50, t1_weight: float = 0.5, t2_weight: float = 0.5):
    """
    Evaluates Reward-to-Risk ratio against minimum breakeven threshold for a given win rate:
      - Min Breakeven R:R = (1 - Win Rate) / Win Rate
      - Multi-target weighted R:R and Expected Value (EV)
    """
    if entry <= 0:
        raise ValueError("Entry price must be positive")
    if stop >= entry:
        raise ValueError(f"Stop loss (₹{stop}) must be below entry (₹{entry})")
    if target_1 <= entry:
        raise ValueError(f"Target 1 (₹{target_1}) must be above entry (₹{entry})")

    risk_per_share = entry - stop
    rew_1 = target_1 - entry
    rr_1 = rew_1 / risk_per_share

    if target_2 and target_2 > entry:
        rew_2 = target_2 - entry
        rr_2 = rew_2 / risk_per_share
        tot_w = t1_weight + t2_weight
        w1 = t1_weight / tot_w
        w2 = t2_weight / tot_w
        weighted_reward = (w1 * rew_1) + (w2 * rew_2)
        weighted_rr = round((w1 * rr_1) + (w2 * rr_2), 2)
    else:
        weighted_reward = rew_1
        weighted_rr = round(rr_1, 2)

    w = max(0.01, min(0.99, win_rate))
    min_be_rr = round((1.0 - w) / w, 2)
    ev = round((w * weighted_reward) - ((1.0 - w) * risk_per_share), 2)

    is_viable = (weighted_rr >= min_be_rr) and (ev > 0)
    reasons = []
    if weighted_rr < min_be_rr:
        reasons.append(f"Sub-breakeven R:R ({weighted_rr}:1 < {min_be_rr}:1 required for {round(w*100)}% win rate)")
    if ev <= 0:
        reasons.append(f"Negative Expected Value (EV = ₹{ev:.2f}/share)")

    return {
        "entry": entry,
        "stop": stop,
        "risk_per_share": round(risk_per_share, 2),
        "target_1": target_1,
        "target_2": target_2,
        "weighted_reward": round(weighted_reward, 2),
        "weighted_rr": weighted_rr,
        "min_breakeven_rr": min_be_rr,
        "ev_per_share": ev,
        "is_viable": is_viable,
        "reasons": reasons if reasons else ["R:R and Expected Value meet trade profitability thresholds."]
    }


def check_order_risk(symbol, qty, entry, stop, realized_loss_today=0, trades_today=0, target_1=None, target_2=None, win_rate=0.50):
    cfg = load_config()
    reasons = []
    passed = True

    now_ist = to_ist()
    mkt_open, mkt_msg = is_market_open(now_ist)
    if not mkt_open:
        reasons.append(f"MARKET_CLOSED: {mkt_msg}")
        passed = False

    # Check 15:00 cutoff for new intraday entries
    if now_ist.time() >= datetime.time(15, 0):
        reasons.append(f"TIME_LIMIT: Entries blocked after 15:00 IST (Current: {now_ist.strftime('%H:%M')})")
        passed = False

    # Check Max Trades per Day
    max_trades = cfg.get("max_trades_per_day", 3)
    if trades_today >= max_trades:
        reasons.append(f"TRADES_LIMIT: Reached daily limit of {max_trades} trades")
        passed = False

    # Check Daily Loss
    max_daily_loss = cfg.get("max_daily_loss_inr", 5000)
    if realized_loss_today >= max_daily_loss:
        reasons.append(f"DAILY_LOSS_LIMIT: Realized ₹{realized_loss_today} loss reaches ₹{max_daily_loss} cap")
        passed = False

    # Check Trade Risk
    risk_per_share = abs(entry - stop)
    total_trade_risk = qty * risk_per_share
    max_trade_loss = cfg.get("max_loss_per_trade_inr", 2000)
    if total_trade_risk > max_trade_loss:
        reasons.append(f"TRADE_LOSS_LIMIT: Potential loss ₹{total_trade_risk:.2f} exceeds cap of ₹{max_trade_loss}")
        passed = False

    # Check Lot multiples for Indices
    for idx, details in cfg.get("indices", {}).items():
        if idx in symbol.upper():
            lot = details.get("lot_size", 1)
            if qty % lot != 0:
                reasons.append(f"LOT_SIZE_ERROR: Qty {qty} is not a multiple of {idx} lot size ({lot})")
                passed = False
            break

    # Check R:R and Expected Value if target is provided
    if target_1 is not None:
        rr_eval = evaluate_rr_and_ev(entry=entry, stop=stop, target_1=target_1, target_2=target_2, win_rate=win_rate)
        if not rr_eval["is_viable"]:
            reasons.append(f"RR_EV_REJECTED: {'; '.join(rr_eval['reasons'])}")
            passed = False

    return {
        "status": "PASS" if passed else "BLOCK",
        "symbol": symbol,
        "qty": qty,
        "potential_loss_inr": round(total_trade_risk, 2),
        "reasons": reasons if reasons else ["All risk parameters passed successfully."]
    }


def main():
    parser = argparse.ArgumentParser(description="Indian Market Risk Gatekeeper (with EV & R:R)")
    parser.add_argument("--symbol", default="NIFTY", help="Trading Symbol")
    parser.add_argument("--qty", type=int, required=True, help="Order quantity")
    parser.add_argument("--entry", type=float, required=True, help="Entry price (₹)")
    parser.add_argument("--stop", type=float, required=True, help="Stop loss price (₹)")
    parser.add_argument("--target-1", type=float, help="Primary Target 1 price (₹)")
    parser.add_argument("--target-2", type=float, help="Secondary Target 2 price (₹)")
    parser.add_argument("--win-rate", type=float, default=0.50, help="Historical win rate (default 0.50 = 50%%)")
    parser.add_argument("--realized-loss", type=float, default=0, help="Loss already realized today (₹)")
    parser.add_argument("--trades", type=int, default=0, help="Number of trades executed today")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    res = check_order_risk(
        symbol=args.symbol,
        qty=args.qty,
        entry=args.entry,
        stop=args.stop,
        realized_loss_today=args.realized_loss,
        trades_today=args.trades,
        target_1=args.target_1,
        target_2=args.target_2,
        win_rate=args.win_rate
    )

    if args.json:
        print(json.dumps(res, indent=2))
        return

    print("=" * 60)
    print("🛡️ INDIAN TRADING RISK GATEKEEPER CHECK")
    print("=" * 60)
    badge = "🟢 PASS" if res["status"] == "PASS" else "🔴 BLOCK"
    print(f"Result:             {badge}")
    print(f"Symbol:             {res['symbol']}")
    print(f"Qty:                {res['qty']}")
    print(f"Max Trade Risk:     ₹{res['potential_loss_inr']:,.2f}")
    print("\nReasons / Checks:")
    for r in res["reasons"]:
        print(f"  • {r}")


if __name__ == "__main__":
    main()
