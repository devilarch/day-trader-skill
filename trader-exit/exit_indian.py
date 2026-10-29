#!/usr/bin/env python3
"""Indian Market Exit & Trade Plan Generator for trader-exit. Standard library only.

Plans stop-loss, take-profit, and intraday flat-by time for Indian trades:
  - Default Stop: Opening Range Midpoint or ATR-based.
  - Default Target: 1R or 2R (Reward-to-Risk).
  - Square-off time: 15:15 IST (Enforced before market close at 15:30 IST).
"""

import argparse
import datetime
import json
import os
import sys

def plan_exit(symbol, entry, or_high=None, or_low=None, risk_reward=1.5, support=None, r1=None, r2=None):
    # Anchor Stop-Loss to validated Support
    if support:
        stop = round(support, 2)
    elif or_high and or_low:
        midpoint = (or_high + or_low) / 2.0
        stop = round(midpoint, 2)
    else:
        # Default 0.8% structural buffer if support not specified
        stop = round(entry * 0.992, 2)

    risk_per_share = round(entry - stop, 2)
    if risk_per_share <= 0:
        raise ValueError(f"Stop loss ({stop}) must be below entry price ({entry})")

    # Anchor Target 1 to Resistance 1 (R1) - De-risking target
    if r1:
        target_1 = round(r1, 2)
    else:
        target_1 = round(entry + (risk_per_share * 1.0), 2)

    # Anchor Target 2 to Resistance 2 (R2) - Breakout runner target
    if r2:
        target_2 = round(r2, 2)
    else:
        target_2 = round(entry + (risk_per_share * risk_reward), 2)

    reward_t1 = round(target_1 - entry, 2)
    reward_t2 = round(target_2 - entry, 2)

    plan = {
        "symbol": symbol,
        "entry": entry,
        "stop_loss": stop,
        "target_1": target_1,
        "target_2": target_2,
        "risk_per_share": risk_per_share,
        "reward_t1": reward_t1,
        "reward_t2": reward_t2,
        "rr_t1": f"{round(reward_t1 / risk_per_share, 2) if risk_per_share else 0}:1",
        "rr_t2": f"{round(reward_t2 / risk_per_share, 2) if risk_per_share else 0}:1",
        "flat_by_time": "15:15 IST",
        "market_close": "15:30 IST"
    }
    return plan

def main():
    parser = argparse.ArgumentParser(description="Indian Market Exit & Target Planner (S/R Anchored)")
    parser.add_argument("--symbol", default="NIFTY", help="Symbol")
    parser.add_argument("--entry", type=float, required=True, help="Entry price (₹)")
    parser.add_argument("--support", type=float, help="Validated key support price / SL anchor (₹)")
    parser.add_argument("--r1", type=float, help="Primary resistance level R1 / Target 1 anchor (₹)")
    parser.add_argument("--r2", type=float, help="Secondary resistance level R2 / Target 2 anchor (₹)")
    parser.add_argument("--or-high", type=float, help="Opening range high (₹)")
    parser.add_argument("--or-low", type=float, help="Opening range low (₹)")
    parser.add_argument("--rr", type=float, default=1.5, help="Reward-to-risk ratio for T2 (default 1.5)")
    args = parser.parse_args()

    plan = plan_exit(args.symbol, args.entry, args.or_high, args.or_low, args.rr, args.support, args.r1, args.r2)

    print("=" * 60)
    print("🎯 S/R & VOLUME ANCHORED INTRADAY TRADE EXIT PLAN")
    print("=" * 60)
    print(f"Symbol:           {plan['symbol']}")
    print(f"Entry Price:      ₹{plan['entry']:,.2f}")
    print(f"Stop Loss:        ₹{plan['stop_loss']:,.2f} (Risk: ₹{plan['risk_per_share']:,.2f})")
    print(f"Target 1 (R1):    ₹{plan['target_1']:,.2f} [Reward: ₹{plan['reward_t1']:,.2f} | R:R {plan['rr_t1']}] (Book 50% & Trail SL)")
    print(f"Target 2 (R2):    ₹{plan['target_2']:,.2f} [Reward: ₹{plan['reward_t2']:,.2f} | R:R {plan['rr_t2']}] (Runner / Breakout)")
    print(f"Intraday Flat By: {plan['flat_by_time']} (Market close: {plan['market_close']})")

if __name__ == "__main__":
    main()
