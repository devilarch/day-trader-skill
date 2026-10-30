# Tier 1 Features Implementation Plan for Day Trader Skill

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Tier 1 trading analysis features adapted from `nse-trading-skills` into `day-trader-skill`: (1) 1x cash equity position sizer with strict <2% risk and portfolio limits, (2) hybrid 4-stage trailing stop planner, and (3) Indian equity S/R and volume confirmation engine.

**Architecture:** Extend existing Indian market CLI tools in `trader-budget/size_indian.py` and `trader-exit/exit_indian.py`, and create `trader-analyst/technical_analysis_indian.py`. All tools use standard library Python (no third-party dependencies required), adhere to zero-leverage 1x cash rules, enforce IST market hours, and provide both human-readable terminal output and `--json` exports for pipelining.

**Tech Stack:** Python 3.8+ (standard library: `json`, `math`, `argparse`, `datetime`, `urllib.request`), `unittest`.

**Spec:** Curated Tier 1 features from `Bhala-Srinivash/nse-trading-skills` (skills: `technical-analysis`, `trailing-stops`, `position-sizing`) and persistent project rules (`intraday-sr-volume-rule.md`, `zero-leverage-and-strict-risk-rule.md`, `mandatory-stop-loss-order-rule.md`).

## Global Constraints

- Standard library only (no pip dependencies).
- Zero leverage: 1x cash only, strictly `capital_used <= capital`.
- Total trade risk at stop loss strictly `< 2%` of capital.
- Single stock position allocation capped at 20% of account capital.
- Currency in Indian Rupees (INR ₹) and timezone in IST (Asia/Kolkata).
- Every tool supports `--json` output for automated pipeline consumption.

## Review Focus

- Capital used exceeds account cash when price is close to stop (must cap shares by total cash and single-stock cap).
- Stop loss placed above entry or at zero (must raise ValueError or reject trade).
- Current volume is None or zero (must gracefully handle missing volume with fallback to 1.0 ratio).
- Trailing stop ratchet moving backward when price retraces (must strictly never allow stop to decrease for longs).
- Fewer than 2 touches for S/R candidate levels (must require >= 2 touches within price tolerance window).

---

### Task 1: 1x Cash Equity Position Sizer with Strict Risk & Portfolio Caps

**Files:**
- Modify: `trader-budget/size_indian.py`
- Create: `tests/test_size_indian.py`

**Interfaces:**
- Produces: `calculate_cash_equity_shares(capital: float, risk_pct: float, entry: float, stop: float, max_loss_inr: float = None, single_stock_cap_pct: float = 0.20) -> dict`

- [ ] **Step 1: Write failing unit tests for cash equity position sizing**

Create `tests/test_size_indian.py` testing:
1. Standard sizing: account ₹100,000, 1.5% risk (₹1,500), entry ₹1,000, stop ₹950 (₹50 risk/share) -> 30 shares, capital ₹30,000 (30%), max risk ₹1,500 (1.5%).
2. Single stock cap: account ₹100,000, 2% risk, entry ₹500, stop ₹495 (₹5 risk/share). Risk would allow 400 shares (₹200,000), but 20% cap restricts capital to ₹20,000 -> 40 shares.
3. 1x Cash hard boundary: account ₹50,000, entry ₹1,000, stop ₹990. Risk allows 100 shares (₹100,000), but available cash restricts to 50 shares (₹50,000).
4. Strict <2% risk violation refusal: if user requests risk_pct >= 2.0%, clamp or reject to enforce strict <2% rule.
5. Invalid stop (stop >= entry) raises ValueError.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_size_indian.py -v`
Expected: FAIL with `ImportError` or `AttributeError: calculate_cash_equity_shares not found`.

- [ ] **Step 3: Implement `calculate_cash_equity_shares` and CLI flags in `trader-budget/size_indian.py`**

Add `calculate_cash_equity_shares` function:
- Cap risk percentage strictly below 2.0% (default 1.5%, error if > 1.99%).
- Compute:
  `risk_per_share = entry - stop` (validate `risk_per_share > 0`)
  `max_loss_inr = min(capital * (risk_pct / 100.0), max_loss_inr or float('inf'))`
  `shares_by_risk = math.floor(max_loss_inr / risk_per_share)`
  `shares_by_cap = math.floor((capital * single_stock_cap_pct) / entry)`
  `shares_by_cash = math.floor(capital / entry)`
  `shares = min(shares_by_risk, shares_by_cap, shares_by_cash)`
- Return dict with `shares`, `capital_used_inr`, `capital_pct`, `max_loss_inr`, `risk_pct_actual`, `limiting_factor`, `status`.
- Add `--mode {cash,options}` argument in `main()`, defaulting to `cash`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests/test_size_indian.py -v`
Expected: PASS (all tests ok).

- [ ] **Step 5: Commit changes**

```bash
git -C /Users/fahimahmad/comp/day-trader-skill add trader-budget/size_indian.py tests/test_size_indian.py
git -C /Users/fahimahmad/comp/day-trader-skill commit -m "feat(budget): add 1x cash equity sizing with strict <2% risk and 20% portfolio cap"
```

---

### Task 2: Hybrid 4-Stage Trailing Stop System

**Files:**
- Modify: `trader-exit/exit_indian.py`
- Create: `tests/test_exit_indian.py`

**Interfaces:**
- Produces:
  - `calculate_trailing_stop(entry: float, initial_stop: float, current_price: float, highest_price: float, atr: float = None, swing_low: float = None) -> dict`
  - Enhanced `plan_exit` including `trailing_plan` dict.

- [ ] **Step 1: Write failing unit tests for trailing stop planner**

Create `tests/test_exit_indian.py` testing:
1. Stage 1 (0 to <1R): Entry ₹100, Stop ₹90 (1R = ₹10). Current ₹105 (0.5R) -> Stop remains ₹90 (Stage 1: Fixed).
2. Stage 2 (1R gained): Current ₹110 (1.0R), Highest ₹110 -> Stop moves to Breakeven ₹100 (Stage 2: Breakeven).
3. Stage 3 (2R gained): Current ₹122 (2.2R), Highest ₹125, ATR=₹4 -> ATR Trail `125 - (1.5 * 4) = 119` (Stage 3: ATR Trail).
4. Stage 4 (3R+ gained): Current ₹135 (3.5R), Highest ₹136, Swing low ₹130 -> Stop moves to ₹130 (Stage 4: Structure Trail).
5. Ratchet rule: If price was ₹125 (Stop ₹119) and drops to ₹121, Stop MUST NOT drop below ₹119.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_exit_indian.py -v`
Expected: FAIL with `ImportError` or `AttributeError`.

- [ ] **Step 3: Implement `calculate_trailing_stop` and update `plan_exit` in `trader-exit/exit_indian.py`**

- Implement `calculate_trailing_stop`:
  - Calculate `1R = entry - initial_stop`.
  - Calculate `r_multiple = (highest_price - entry) / 1R`.
  - Apply stage conditions:
    - `r_multiple < 1.0`: Stage 1 (Fixed stop).
    - `1.0 <= r_multiple < 2.0`: Stage 2 (Breakeven: `entry`).
    - `2.0 <= r_multiple < 3.0`: Stage 3 (ATR trail: `max(entry, highest_price - (1.5 * (atr or (0.5 * 1R))))`).
    - `r_multiple >= 3.0`: Stage 4 (Structure trail: `max(atr_trail, swing_low or (highest_price - 1R))`).
  - Ensure stop is strictly $\ge \text{initial\_stop}$ and never ratchets down.
- Add `trailing_plan` into `plan_exit` output with thresholds for Breakeven (+1R), ATR Trail (+2R), and Structure Trail (+3R).
- Add CLI options: `--trail`, `--current-price`, `--highest-price`, `--atr`, `--swing-low`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests/test_exit_indian.py -v`
Expected: PASS (all tests ok).

- [ ] **Step 5: Commit changes**

```bash
git -C /Users/fahimahmad/comp/day-trader-skill add trader-exit/exit_indian.py tests/test_exit_indian.py
git -C /Users/fahimahmad/comp/day-trader-skill commit -m "feat(exit): add hybrid 4-stage trailing stop planner and ratchet engine"
```

---

### Task 3: Indian Equity Technical S/R & Volume Analysis Engine

**Files:**
- Create: `trader-analyst/technical_analysis_indian.py`
- Create: `tests/test_technical_analysis_indian.py`

**Interfaces:**
- Produces:
  - `identify_sr_levels(candles: list, current_price: float, min_touches: int = 2) -> dict`
  - `analyze_volume(candles: list, current_volume: float = None) -> dict`
  - `generate_technical_assessment(symbol: str, candles: list, current_price: float = None, current_volume: float = None) -> dict`

- [ ] **Step 1: Write failing unit tests for S/R and volume engine**

Create `tests/test_technical_analysis_indian.py` testing:
1. S/R Identification: Detects swing highs touched $\ge 2$ times within 0.5% tolerance as resistance, and swing lows touched $\ge 2$ times as support.
2. Volume Confirmation:
   - Volume > 1.5× 20-DMA volume flagged as `CONFIRMED_VOLUME` (ratio $> 1.5$).
   - Volume < 0.8× 20-DMA volume flagged as `LOW_VOLUME_WARNING` (ratio $< 0.8$).
3. Moving Average Alignment: Calculates SMA20, SMA50, SMA200 and determines trend state (Uptrend if Price > SMA20 > SMA50 > SMA200).
4. Probabilistic Scenarios: Outputs Scenario A (Bullish % with target at R1), Scenario B (Bearish % with invalidation at S1).

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_technical_analysis_indian.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'trader-analyst.technical_analysis_indian'`.

- [ ] **Step 3: Implement `trader-analyst/technical_analysis_indian.py`**

- Support both offline candle lists and fetching online daily/hourly charts via Yahoo Finance (`.NS` ticker convention).
- Implement S/R clustering algorithm:
  - Group local extrema within 0.5% tolerance.
  - Require $\ge \text{min\_touches}$ (default 2) to qualify as a verified level.
  - Identify nearest verified support below current price and nearest resistance above current price.
- Implement volume analyzer:
  - Calculate 20-period SMA of volume.
  - Return `volume_ratio = current_volume / avg_volume` and status string (`CONFIRMED_BREAKOUT`, `EXHAUSTION_RALLY`, etc.).
- Implement probabilistic scenario generator (Bullish / Bearish / Sideways summing to 100%).
- Provide full CLI with `--symbol`, `--candles-file`, `--json`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests/test_technical_analysis_indian.py -v`
Expected: PASS (all tests ok).

- [ ] **Step 5: Commit changes**

```bash
git -C /Users/fahimahmad/comp/day-trader-skill add trader-analyst/technical_analysis_indian.py tests/test_technical_analysis_indian.py
git -C /Users/fahimahmad/comp/day-trader-skill commit -m "feat(analyst): add Indian equity S/R mapping and volume confirmation engine"
```

---

### Task 4: Documentation and Skill Integration

**Files:**
- Modify: `trader-budget/SKILL.md`
- Modify: `trader-exit/SKILL.md`
- Modify: `trader-analyst/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Update skill manuals**
  - Add `size_indian.py --mode cash` examples to `trader-budget/SKILL.md`.
  - Add `exit_indian.py --trail` 4-stage trailing stop reference to `trader-exit/SKILL.md`.
  - Add `technical_analysis_indian.py` usage and Indian market S/R & volume analysis to `trader-analyst/SKILL.md`.
  - Update `README.md` summary table.

- [ ] **Step 2: Run the full new test suite**

Run: `python3 -m unittest discover -s tests -p "test_*_indian.py" -v`
Expected: PASS on all Indian market test suites.

- [ ] **Step 3: Commit documentation updates**

```bash
git -C /Users/fahimahmad/comp/day-trader-skill add trader-budget/SKILL.md trader-exit/SKILL.md trader-analyst/SKILL.md README.md
git -C /Users/fahimahmad/comp/day-trader-skill commit -m "docs: document Tier 1 Indian trading features (cash sizing, trailing stops, S/R volume engine)"
```
