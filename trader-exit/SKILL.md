---
name: trader-exit
description: >-
  Exit Planner. Sets your stop and your target before you enter, so you know
  when to get out. Reads the entry from trader-entry (or a price you give),
  puts the stop at the opening-range midpoint by default (or the range low,
  your price, a percent, or a multiple of the ATR), rounds it down to the
  cent, and sets the target at 2R (or 1R, or your price). Refuses a stop at or
  above the entry, a target at or below it, or a stop too tight to survive the
  spread, and says why. Writes trader/plan.json for the Time Machine, the
  Budget Manager and Price Alerts. Long side only. Use when the user says
  "where's my stop", "set my stop and target", "plan the exit", "when do I get
  out", "stop loss", "what's my R", "risk reward", or right after
  /trader-entry triggers, before /trader-timemachine.
argument-hint: "[--stop or-mid|or-low|price:X|pct:X|atr:K] [--target 2R|1R|price:X]"
---

# trader-exit

The Exit Planner decides how a trade ends before it starts. The stop is where
the setup has failed. The target is where you take what you came for. Both
are set BEFORE the entry, written down and handed on, so nobody has to decide
anything in the middle of a fast move. A stop is a plan, not a guarantee: a
gap or a fast market can fill past it. Day trading loses most people money,
and a neat plan does not change that.

`${CLAUDE_SKILL_DIR}` below is this skill's folder (where this SKILL.md lives).

```bash
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan                          # trader/entry.json: midpoint stop, 2R target
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop or-mid --target 1R --write
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop atr:1.5           # needs the session's bars (Yahoo or --offline)
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --symbol TSLA --entry 364.18 --or-high 362.18 --or-low 354.47
python3 "${CLAUDE_SKILL_DIR}/exit.py" show                          # the current trader/plan.json
```

Other flags: `--flat-by 15:55`, `--json`, `--now "2026-10-19 10:15"` (New
York time), `--entry PRICE` with a waiting entry.json to plan ahead, `--setup
level`, `--offline FILE` (a saved Yahoo chart JSON for an ATR stop).

## What it reads and writes

| file | what |
| --- | --- |
| `trader/entry.json` | the trigger from trader-entry: symbol, entry price, time, bar, opening range |
| `trader/config.json` | `flat_by` (15:55) and `min_reward_risk` (1.0: a note here, trader-risk enforces it) |
| Yahoo chart API | only for an `atr:K` stop: the session's bars up to the entry bar, free and unofficial |
| `trader/plan.json` | with `--write`: entry, stop and its rule, target and its R, risk a share, reward:risk, flat by. trader-timemachine, trader-budget and trader-alerts read it |

## Indian Market Exit & Hybrid Trailing Stops (`exit_indian.py`)

For NSE/BSE intraday planning with S/R levels and progressive 4-stage trailing stops:

```bash
# Generate S/R anchored exit plan with 4-stage trailing roadmap
python3 "${CLAUDE_SKILL_DIR}/exit_indian.py" --symbol INFY --entry 1800 --support 1760 --r1 1840 --r2 1880

# Generate Fibonacci-anchored exit plan (Retracements 38.2%-61.8% & Extensions 127.2%-161.8%)
python3 "${CLAUDE_SKILL_DIR}/exit_indian.py" --symbol INFY --entry 1800 --fib-high 1950 --fib-low 1700 --fib-c 1750

# Evaluate active trailing stop stage during trade execution
python3 "${CLAUDE_SKILL_DIR}/exit_indian.py" --symbol INFY --entry 1800 --support 1760 --trail --current-price 1890 --highest-price 1900 --atr 20
```

### Fibonacci Retracements & Extensions
- **Retracement Zones:** 23.6%, 38.2%, 50.0%, 61.8% (Golden Ratio entry/stop zone), and 78.6% (invalidation).
- **Extension Targets:** 100% (measured swing move), 127.2% (conservative target 1), and 161.8% (standard runner target 2).

### The 4-Stage Progressive Trailing Stop Model:
- **Stage 1 (0 to <1R):** Hold initial stop fixed at support (protects against premature shakeout).
- **Stage 2 (+1R gain):** Move stop strictly to **Breakeven** (entry price).
- **Stage 3 (+2R gain):** Engage **ATR Trail** (`Highest Close - 1.5x ATR`).
- **Stage 4 (+3R+ gain):** Engage **Structure Trail** (ratchet stop below recent 5m/15m swing low).
- **Ratchet Rule:** Trailing stops strictly move only up for longs, never downward.

## Stops and targets

### Mandatory Resistance & Support Anchoring
Targets and stop-losses must NEVER be calculated purely through abstract arithmetic.
They must always be cross-referenced with concrete chart levels and volume:
1. **Target 1 (Primary / De-risking Target):** Must be placed immediately below
   the nearest major resistance band (R1) or swing high where selling pressure /
   rejection volume previously appeared. Used to book partial profit (50%-70%)
   and move Stop-Loss to breakeven (cost).
2. **Target 2 (Runner / Breakout Target):** Placed at secondary resistance (R2)
   or the expanded target, achievable only if R1 is breached with strong volume.
3. **Stop-Loss (Structural S/L):** Placed directly beneath key structural support
   (S1, VWAP, or consolidation low), never arbitrarily, ensuring the trade setup
   remains invalid if hit while preventing premature stop-outs by normal noise.

| stop | where it goes |
| --- | --- |
| `or-mid` | the opening-range midpoint (the default for an opening-range breakout) |
| `or-low` | the opening-range low: wider, so fewer shares for the same max loss |
| `price:X` | your price |
| `pct:X` | X percent under the entry |
| `atr:K` | K times the 14-bar ATR under the entry, on the session's bars up to the entry bar. With fewer than 14 bars by then it averages all of them and says so |

A level setup has no opening range to lean on, so it needs a stop you name.

- **Rounding.** The stop rounds AWAY from the entry to the cent (down, for a
  long). Risk = entry minus stop. Target = entry + R x risk, rounded half up
  to the cent. `2R` by default; `1R`, `1.5R` or `price:X` also work.
- **Refused, with the reason.** A stop at or above the entry. A target at or
  below it. A risk under 0.05% of the price: too tight to survive the
  spread, normal wiggle would stop you out. An entry.json that has not
  triggered (unless you give `--entry`). A short: v2 plans longs only.
- **Flat by.** 15:55 by default (or `flat_by` in the config). Out by then,
  win or lose, no overnight hold. On a 1:00 p.m. early close it moves up to
  12:55. An entry at or after the flat-by time is refused.

## Steps

1. Run it right after `/trader-entry` triggers. Before that, `--entry PRICE`
   plans ahead at the level you expect.
2. Use the default stop for an opening-range breakout unless the user names
   another. A level setup needs one: ask.
3. Run `exit.py plan --write`. Read back the entry, the stop and its rule,
   the target and its rule, the risk a share, reward:risk and flat by.
4. If it refuses, say the reason and the fix (a wider stop, a farther
   target). Never loosen anything on your own.
5. Say once that the stop is a plan, not a guarantee.
6. Hand off to `/trader-timemachine` to replay the plan, then `/trader-budget`
   to size it to the max loss per trade. Offer `/trader-alerts` for the stop,
   the target and the flat-by time. Claude can keep `entry.py watch` running
   in the background or on a `/loop` until a setup triggers, then come here.

## Example: the reel

TSLA, Monday 2026-10-19. The entry is 364.18 at 10:15 AM (the 10:10 bar,
bar 8) and the opening range is 354.47 to 362.18. `exit.py plan --stop
or-mid --target 1R --write`:

```
Exit plan: TSLA long, Mon 2026-10-19, opening-range breakout on 5-minute bars
  Entry         $364.18 at 10:15 AM (bar 8)
  Stop          $358.32  opening-range midpoint: ($362.18 + $354.47) / 2 = $358.325, rounded down
  Target        $370.04  1R (one times the risk)
  Risk a share  $5.86 (1.61% of the entry)
  Reward:risk   1.0
  Flat by       15:55 ET, win or lose: no overnight hold
```

The default 2R target would be 364.18 + 2 x 5.86 = 375.90. trader-budget then
sizes it: a $50 max loss per trade buys floor(50 / 5.86) = 8 shares.

## Rules

- The stop and the target are set before the entry, never after.
- Never move a stop further from the entry once the trade is on.
- Plain numbers only: entry, stop, target, risk a share, reward:risk. It
  never prints a P&L or a return.
- Nothing here promises winning trades or money. A 1R target is not a
  prediction that the price gets there.
- Long side only. v2 plans longs only.

## What it never does

It never places an order, never sizes a position, never widens a stop to
make a plan pass, and never calls a stop a guarantee.

## Safety

- Education and tooling, not financial advice. A PASS is a rules check, not a recommendation.
- Paper trading by default (`"paper": true`). Going live is the user's own decision, in their own config.
- Nothing in this pack places an order except trader-broker, and only when all three hold: trader-risk
  passed that exact order today, the user typed an explicit yes for that one order in the chat, and the
  user clicked Allow once on Claude's own card because the order tool is set to "Needs approval"
  (Customize > Connectors > tool permissions). Never set an order tool to "Always allow".
- No options, margin, short selling or leverage unless the config allows it and the user confirms.
- Broker keys live in environment variables or the Claude Desktop config, never in the chat.
