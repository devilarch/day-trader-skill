# Tier 3 Features Implementation Plan for Day Trader Skill

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Tier 3 trading features adapted from `nse-trading-skills` into `day-trader-skill`: (1) Expected Value (EV) and win-rate-based R:R trade gatekeeper in `trader-risk/check_indian.py`, and (2) standardized probabilistic action plan table formatter in `trader-analyst/technical_analysis_indian.py`.

**Architecture:** Extend existing Indian market tools using standard library Python. All calculations are deterministic arithmetic.

**Tech Stack:** Python 3.8+ (standard library: `math`, `json`, `argparse`, `datetime`), `unittest`.

**Spec:** Curated Tier 3 features from `Bhala-Srinivash/nse-trading-skills` (skills: `risk-reward-ratio`, `nse-trading-toolkit`).

## Global Constraints

- Standard library only (no pip dependencies).
- Zero leverage: 1x cash trading.
- Rejects negative EV or sub-breakeven R:R trades before order placement.
- Clean JSON and formatted terminal table output.
- All code tested with failing tests first (TDD).

## Review Focus

- Win rate <= 0 or >= 1.0 (clamped or raises ValueError).
- Target below entry on long trade (raises ValueError).
- Stop above entry on long trade (raises ValueError).
- Sizing dict missing optional fields (handled with defaults).

---

### Task 1: Expected Value (EV) & Win-Rate R:R Gatekeeper

**Files:**
- Modify: `trader-risk/check_indian.py`
- Create: `tests/test_risk_indian.py`

**Interfaces:**
- Produces:
  - `calculate_expected_value(win_rate: float, avg_win: float, avg_loss: float) -> dict`
  - `evaluate_rr_and_ev(entry: float, stop: float, target_1: float, target_2: float = None, win_rate: float = 0.50, t1_weight: float = 0.5, t2_weight: float = 0.5) -> dict`
  - Enhanced `check_order_risk(...)` with EV/RR validation.

- [ ] **Step 1: Write failing unit tests for EV and R:R evaluation**

Create `tests/test_risk_indian.py` testing:
1. Standard EV calculation: win rate 50%, avg win ₹300, avg loss ₹100 -> EV = +₹100 (positive edge).
2. Negative EV rejection: win rate 40%, avg win ₹100, avg loss ₹100 -> EV = -₹20 (negative EV rejected).
3. Minimum R:R by win rate:
   - 40% win rate requires min 1.50:1 R:R (trade with 1.2:1 rejected).
   - 50% win rate requires min 1.00:1 R:R.
4. Multi-target weighted R:R: T1 (50%) at 1:1, T2 (50%) at 2:1 -> Weighted R:R = 1.5:1.
5. Integration with `check_order_risk`: Sub-breakeven trade returns `status: "BLOCK"` with reason `RR_EV_REJECTED`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_risk_indian.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement EV/RR functions and update `check_order_risk` in `trader-risk/check_indian.py`**

- Implement `calculate_expected_value`:
  - `EV = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)`
- Implement `evaluate_rr_and_ev`:
  - Breakeven min R:R table: `(1 - W) / W`.
  - Weighted reward calculation.
  - Returns viability and status.
- Hook into `check_order_risk`:
  - If targets supplied, evaluate EV and R:R. Block order if negative EV or below min R:R.
- Add CLI args: `--target-1`, `--target-2`, `--win-rate`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests/test_risk_indian.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git -C /Users/fahimahmad/comp/day-trader-skill add trader-risk/check_indian.py tests/test_risk_indian.py
git -C /Users/fahimahmad/comp/day-trader-skill commit -m "feat(risk): add Expected Value (EV) and win-rate R:R gatekeeper"
```

---

### Task 2: Standardized Action Plan Table Formatter

**Files:**
- Modify: `trader-analyst/technical_analysis_indian.py`
- Create: `tests/test_action_plan_indian.py`

**Interfaces:**
- Produces: `format_action_plan_table(assessment: dict, plan: dict = None, sizing: dict = None) -> str`

- [ ] **Step 1: Write failing unit test for action plan table**

Create `tests/test_action_plan_indian.py` testing:
1. Markdown table output includes columns: `Action`, `Trigger`, `Price`, `Size`, `Stop`, `Target`, `R:R`.
2. Formats all 3 scenarios into structured actions (Buy on breakout, Sell/Short on breakdown, Hold/Wait in range).

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_action_plan_indian.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `format_action_plan_table` in `trader-analyst/technical_analysis_indian.py`**

- Add formatter producing markdown table.
- Add CLI argument `--action-plan`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests/test_action_plan_indian.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git -C /Users/fahimahmad/comp/day-trader-skill add trader-analyst/technical_analysis_indian.py tests/test_action_plan_indian.py
git -C /Users/fahimahmad/comp/day-trader-skill commit -m "feat(analyst): add standardized markdown action plan table formatter"
```

---

### Task 3: Documentation and Verification

**Files:**
- Modify: `trader-risk/SKILL.md`
- Modify: `trader-analyst/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Update skill manuals and README**
- [ ] **Step 2: Run all Indian test suites**
- [ ] **Step 3: Commit and push changes**
