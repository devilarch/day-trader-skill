#!/usr/bin/env python3
"""Indian Market Exit & Trade Plan Generator for trader-exit. Standard library only.

Plans stop-loss, take-profit, hybrid 4-stage trailing stop, and intraday flat-by time:
  - Default Stop: Opening Range Midpoint, Validated Support, or ATR buffer.
  - Hybrid 4-Stage Trailing Stop:
      Stage 1 (0 to <1R): Fixed initial stop.
      Stage 2 (At +1R): Move stop to Breakeven (entry price).
      Stage 3 (At +2R): ATR Trail (Highest Close - 1.5x ATR).
      Stage 4 (At +3R+): Structure Trail (Recent swing low).
  - Square-off time: 15:15 IST (Enforced before market close at 15:30 IST).
"""

import argparse
import datetime
import json
import os
import sys


def calculate_trailing_stop(entry: float, initial_stop: float, current_price: float, highest_price: float = None, atr: float = None, swing_low: float = None):
    """
    Evaluates current trade stage and computes the ratcheted trailing stop price:
      - Never allows the stop loss to decrease (ratchet rule).
      - Returns stage index (1-4), stage name, trailing stop price, and rationale.
    """
    if entry <= 0:
        raise ValueError("Entry price must be positive")
    if initial_stop >= entry:
        raise ValueError(f"Initial stop ({initial_stop}) must be below entry ({entry})")

    risk_per_share = entry - initial_stop
    peak_price = max(entry, highest_price or current_price)
    gain_at_peak = peak_price - entry
    r_multiple = round(gain_at_peak / risk_per_share, 2) if risk_per_share > 0 else 0.0

    atr_val = atr if (atr is not None and atr > 0) else (0.5 * risk_per_share)

    if r_multiple < 1.0:
        stage = 1
        stage_name = "Fixed Initial Stop"
        trailing_stop = initial_stop
        rationale = f"Peak gain {r_multiple}R < 1.0R. Hold fixed initial stop to avoid noise shakeouts."
    elif 1.0 <= r_multiple < 2.0:
        stage = 2
        stage_name = "Breakeven"
        trailing_stop = entry
        rationale = f"Peak gain {r_multiple}R >= 1.0R. Stop moved to breakeven (₹{entry:,.2f}) to eliminate capital risk."
    elif 2.0 <= r_multiple < 3.0:
        stage = 3
        stage_name = "ATR Trail"
        raw_stop = round(peak_price - (1.5 * atr_val), 2)
        trailing_stop = max(entry, raw_stop)
        rationale = f"Peak gain {r_multiple}R >= 2.0R. Stop trailed at 1.5x ATR below peak (₹{trailing_stop:,.2f})."
    else:
        stage = 4
        stage_name = "Structure Trail"
        raw_atr_stop = round(peak_price - (1.5 * atr_val), 2)
        if swing_low and swing_low > entry:
            trailing_stop = round(max(raw_atr_stop, swing_low), 2)
        else:
            trailing_stop = max(entry, raw_atr_stop)
        rationale = f"Peak gain {r_multiple}R >= 3.0R runner. Trailing stop ratcheted below swing structure (₹{trailing_stop:,.2f})."

    # Enforce strict ratchet: stop can never drop below initial stop
    trailing_stop = round(max(initial_stop, trailing_stop), 2)

    return {
        "stage": stage,
        "stage_name": stage_name,
        "entry": entry,
        "initial_stop": initial_stop,
        "current_price": current_price,
        "highest_price": peak_price,
        "trailing_stop": trailing_stop,
        "r_multiple_gained": r_multiple,
        "rationale": rationale
    }


def plan_exit(symbol, entry, or_high=None, or_low=None, risk_reward=1.5, support=None, r1=None, r2=None, atr=None):
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

    # Progressive 4-Stage Trailing Stop Plan
    trailing_plan = {
        "stage_1_initial_stop": stop,
        "stage_2_breakeven_trigger": round(entry + (risk_per_share * 1.0), 2),
        "stage_3_atr_trail_trigger": round(entry + (risk_per_share * 2.0), 2),
        "stage_4_structure_trigger": round(entry + (risk_per_share * 3.0), 2),
        "atr_multiplier": 1.5,
        "rules": [
            "Stage 1 (0 to <1R): Keep initial stop fixed.",
            "Stage 2 (At +1R gain): Move stop to breakeven (entry price).",
            "Stage 3 (At +2R gain): Trail at Highest Close - 1.5x ATR.",
            "Stage 4 (At +3R+ gain): Trail below most recent swing low structure."
        ]
    }

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
        "trailing_plan": trailing_plan,
        "flat_by_time": "15:15 IST",
        "market_close": "15:30 IST"
    }
    return plan


def main():
    parser = argparse.ArgumentParser(description="Indian Market Exit & Target Planner (S/R Anchored & Trailing)")
    parser.add_argument("--symbol", default="NIFTY", help="Symbol")
    parser.add_argument("--entry", type=float, required=True, help="Entry price (₹)")
    parser.add_argument("--support", type=float, help="Validated key support price / SL anchor (₹)")
    parser.add_argument("--r1", type=float, help="Primary resistance level R1 / Target 1 anchor (₹)")
    parser.add_argument("--r2", type=float, help="Secondary resistance level R2 / Target 2 anchor (₹)")
    parser.add_argument("--or-high", type=float, help="Opening range high (₹)")
    parser.add_argument("--or-low", type=float, help="Opening range low (₹)")
    parser.add_argument("--rr", type=float, default=1.5, help="Reward-to-risk ratio for T2 (default 1.5)")
    parser.add_argument("--atr", type=float, help="Average True Range ATR(14) (₹)")
    parser.add_argument("--trail", action="store_true", help="Evaluate current trailing stop stage")
    parser.add_argument("--current-price", type=float, help="Current market price (₹)")
    parser.add_argument("--highest-price", type=float, help="Highest price reached since entry (₹)")
    parser.add_argument("--swing-low", type=float, help="Recent higher swing low (₹)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.trail:
        stop = args.support or (args.entry * 0.992)
        curr = args.current_price or args.entry
        peak = args.highest_price or curr
        res = calculate_trailing_stop(
            entry=args.entry,
            initial_stop=stop,
            current_price=curr,
            highest_price=peak,
            atr=args.atr,
            swing_low=args.swing_low
        )
        if args.json:
            print(json.dumps(res, indent=2))
            return
        print("=" * 60)
        print("🔄 INDIAN MARKET DYNAMIC TRAILING STOP EVALUATION")
        print("=" * 60)
        print(f"Active Stage:         Stage {res['stage']} ({res['stage_name']})")
        print(f"Entry Price:          ₹{res['entry']:,.2f}")
        print(f"Initial Stop:         ₹{res['initial_stop']:,.2f}")
        print(f"Highest Reached:      ₹{res['highest_price']:,.2f} (+{res['r_multiple_gained']}R)")
        print(f"Current Trailing Stop: ₹{res['trailing_stop']:,.2f}")
        print(f"Rationale:            {res['rationale']}")
        return

    plan = plan_exit(args.symbol, args.entry, args.or_high, args.or_low, args.rr, args.support, args.r1, args.r2, args.atr)
    if args.json:
        print(json.dumps(plan, indent=2))
        return

    print("=" * 60)
    print("🎯 S/R & VOLUME ANCHORED INTRADAY TRADE EXIT PLAN")
    print("=" * 60)
    print(f"Symbol:           {plan['symbol']}")
    print(f"Entry Price:      ₹{plan['entry']:,.2f}")
    print(f"Stop Loss:        ₹{plan['stop_loss']:,.2f} (Risk: ₹{plan['risk_per_share']:,.2f})")
    print(f"Target 1 (R1):    ₹{plan['target_1']:,.2f} [Reward: ₹{plan['reward_t1']:,.2f} | R:R {plan['rr_t1']}] (Book 50% & Trail SL)")
    print(f"Target 2 (R2):    ₹{plan['target_2']:,.2f} [Reward: ₹{plan['reward_t2']:,.2f} | R:R {plan['rr_t2']}] (Runner / Breakout)")
    print(f"Intraday Flat By: {plan['flat_by_time']} (Market close: {plan['market_close']})")
    print("-" * 60)
    print("📈 HYBRID 4-STAGE TRAILING STOP ROADMAP:")
    tp = plan["trailing_plan"]
    print(f"  • Stage 1 (0 to <1R): Hold initial SL @ ₹{tp['stage_1_initial_stop']:,.2f}")
    print(f"  • Stage 2 (+1R Gain): At ₹{tp['stage_2_breakeven_trigger']:,.2f} -> Move SL to Breakeven (₹{plan['entry']:,.2f})")
    print(f"  • Stage 3 (+2R Gain): At ₹{tp['stage_3_atr_trail_trigger']:,.2f} -> Trail @ High - 1.5x ATR")
    print(f"  • Stage 4 (+3R Gain): At ₹{tp['stage_4_structure_trigger']:,.2f} -> Trail below 5m/15m swing low")


if __name__ == "__main__":
    main()
