#!/usr/bin/env python3
"""Indian Market Position & Sizer for trader-budget. Standard library only.

Supports two sizing modes:
1. Cash Equity (1x cash, zero leverage, strict <2% total risk, 20% single-stock cap).
2. Index Options (Lot constraints for NIFTY, BANKNIFTY, SENSEX).
"""

import argparse
import json
import math
import os
import sys

INDEX_LOTS = {
    "NIFTY": 25,
    "BANKNIFTY": 15,
    "SENSEX": 10
}


def calculate_cash_equity_shares(
    capital: float,
    risk_pct: float,
    entry: float,
    stop: float,
    max_loss_inr: float = None,
    single_stock_cap_pct: float = 0.20
):
    """
    Computes exact share size for 1x Cash Equity trading on NSE/BSE:
      - Zero leverage: Capital required <= Account cash.
      - Strict Risk Rule: Risk % must be strictly < 2.0% of total capital.
      - Single-stock Cap: Max position size capped at single_stock_cap_pct (default 20%).
    """
    if capital <= 0:
        raise ValueError("Capital must be greater than zero")
    if entry <= 0:
        raise ValueError("Entry price must be greater than zero")
    if stop >= entry:
        raise ValueError(f"Stop loss (₹{stop}) must be below entry price (₹{entry})")
    if risk_pct >= 2.0:
        raise ValueError(f"Risk percentage ({risk_pct}%) must be strictly < 2.0% of capital")

    risk_per_share = entry - stop

    # Allowed rupee risk based on user risk percentage (strictly < 2%)
    max_loss_by_pct = capital * (risk_pct / 100.0)
    allowed_loss = min(max_loss_by_pct, max_loss_inr) if max_loss_inr else max_loss_by_pct

    # Constraints
    shares_by_risk = math.floor(allowed_loss / risk_per_share)
    shares_by_cap = math.floor((capital * single_stock_cap_pct) / entry)
    shares_by_cash = math.floor(capital / entry)  # 1x cash, no leverage

    shares = min(shares_by_risk, shares_by_cap, shares_by_cash)

    # Determine which limit constrained the size
    if shares <= 0:
        limiting_factor = "budget_or_risk_too_small"
        status = "REJECTED (Risk or budget too small for 1 share)"
    elif shares == shares_by_cap and single_stock_cap_pct < 1.0 and shares_by_cap < shares_by_risk:
        limiting_factor = "single_stock_cap"
        status = "APPROVED"
    elif shares == shares_by_cash and shares_by_cash < shares_by_risk:
        limiting_factor = "available_cash"
        status = "APPROVED"
    else:
        limiting_factor = "risk_budget"
        status = "APPROVED"

    capital_used = round(shares * entry, 2)
    max_risk = round(shares * risk_per_share, 2)
    capital_pct = round((capital_used / capital) * 100.0, 2)
    risk_pct_actual = round((max_risk / capital) * 100.0, 2)

    return {
        "mode": "cash_equity",
        "capital": capital,
        "entry": entry,
        "stop": stop,
        "risk_per_share": round(risk_per_share, 2),
        "shares": shares,
        "capital_used_inr": capital_used,
        "capital_pct": capital_pct,
        "max_risk_inr": max_risk,
        "risk_pct_actual": risk_pct_actual,
        "single_stock_cap_pct": round(single_stock_cap_pct * 100.0, 1),
        "limiting_factor": limiting_factor,
        "status": status
    }


def calculate_option_lots(underlying, budget, entry_premium, stop_premium, max_loss):
    """
    Computes exact lot size for Indian Index Options.
    Risk per share = (entry_premium - stop_premium)
    Max loss constraint = max_loss / risk_per_share
    Budget constraint = budget / entry_premium
    """
    clean_und = underlying.upper().replace(" ", "")
    lot_size = 1
    for k, size in INDEX_LOTS.items():
        if k in clean_und:
            lot_size = size
            break

    risk_per_unit = max(0.05, entry_premium - stop_premium)
    max_qty_by_risk = max_loss / risk_per_unit
    max_qty_by_budget = budget / entry_premium

    allowed_qty = min(max_qty_by_risk, max_qty_by_budget)
    lots = int(math.floor(allowed_qty / lot_size))
    total_qty = lots * lot_size
    capital_used = total_qty * entry_premium
    max_rupee_loss = total_qty * risk_per_unit

    return {
        "mode": "index_options",
        "underlying": underlying,
        "lot_size": lot_size,
        "lots": lots,
        "total_qty": total_qty,
        "entry_premium": entry_premium,
        "stop_premium": stop_premium,
        "risk_per_unit": risk_per_unit,
        "capital_used_inr": round(capital_used, 2),
        "max_risk_inr": round(max_rupee_loss, 2),
        "status": "APPROVED" if lots > 0 else "REJECTED (Risk or budget too small for 1 lot)"
    }


def main():
    parser = argparse.ArgumentParser(description="Indian Market Position & Lot Sizer (Cash & Options)")
    parser.add_argument("--mode", choices=["cash", "options"], default="cash", help="Sizing mode (default: cash)")
    parser.add_argument("--symbol", default="RELIANCE", help="Symbol or Underlying")
    parser.add_argument("--entry", type=float, required=True, help="Entry price or option premium (₹)")
    parser.add_argument("--stop", type=float, required=True, help="Stop loss price or premium (₹)")
    parser.add_argument("--capital", type=float, default=100000, help="Total trading capital (₹)")
    parser.add_argument("--risk-pct", type=float, default=1.5, help="Risk percentage of capital (strictly < 2.0)")
    parser.add_argument("--max-loss", type=float, default=None, help="Explicit max rupee loss cap (₹)")
    parser.add_argument("--single-stock-cap", type=float, default=0.20, help="Single stock allocation cap (default 0.20 = 20%%)")
    parser.add_argument("--json", action="store_true", help="Output result as JSON")
    args = parser.parse_args()

    if args.mode == "cash":
        result = calculate_cash_equity_shares(
            capital=args.capital,
            risk_pct=args.risk_pct,
            entry=args.entry,
            stop=args.stop,
            max_loss_inr=args.max_loss,
            single_stock_cap_pct=args.single_stock_cap
        )
        if args.json:
            print(json.dumps(result, indent=2))
            return

        print("=" * 60)
        print("🎯 INDIAN CASH EQUITY POSITION SIZING TICKET (1x CASH)")
        print("=" * 60)
        print(f"Symbol:               {args.symbol}")
        print(f"Status:               {result['status']}")
        print(f"Recommended Shares:   {result['shares']} shares")
        print(f"Capital Required:     ₹{result['capital_used_inr']:,.2f} ({result['capital_pct']}% of account)")
        print(f"Max Risk at Stop:     ₹{result['max_risk_inr']:,.2f} ({result['risk_pct_actual']}% of account)")
        print(f"Limiting Factor:      {result['limiting_factor']}")
        print(f"Single-Stock Cap:     {result['single_stock_cap_pct']}%")
    else:
        max_loss = args.max_loss if args.max_loss else (args.capital * (args.risk_pct / 100.0))
        result = calculate_option_lots(
            underlying=args.symbol,
            budget=args.capital,
            entry_premium=args.entry,
            stop_premium=args.stop,
            max_loss=max_loss
        )
        if args.json:
            print(json.dumps(result, indent=2))
            return

        print("=" * 60)
        print("🎯 INDIAN INDEX OPTION POSITION SIZING TICKET")
        print("=" * 60)
        for k, v in result.items():
            print(f"  {k:20}: {v}")


if __name__ == "__main__":
    main()
