# Tier 2 Features Implementation Plan for Day Trader Skill

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Tier 2 trading features adapted from `nse-trading-skills` into `day-trader-skill`: (1) Fibonacci retracement and extension calculations with S/R confluence, (2) regular and hidden RSI divergence detection, and (3) Elder's 3-screen multi-timeframe 6-point confluence scoring system.

**Architecture:** Extend existing Indian market tools (`trader-exit/exit_indian.py`, `trader-scanner/scan_indian.py`, and `trader-entry/entry_indian.py`) using standard library Python. Each module provides clean analytical functions, CLI parameters, and `--json` outputs.

**Tech Stack:** Python 3.8+ (standard library only: `math`, `json`, `argparse`, `datetime`, `urllib.request`), `unittest`.

**Spec:** Curated Tier 2 features from `Bhala-Srinivash/nse-trading-skills` (skills: `fibonacci-trading`, `rsi-divergence`, `multi-timeframe-analysis`).

## Global Constraints

- Standard library only (no pip dependencies).
- Zero leverage: 1x cash trading.
- All formulas deterministic and mathematical.
- Clean JSON and human-readable terminal output.
- All new functionality tested with unit tests before implementation (TDD).

## Review Focus

- Fibonacci swing high <= swing low (must raise ValueError).
- Insufficient candles for RSI divergence (< 20 candles returns empty list).
- Division by zero in RSI delta calculation when all deltas are gains or losses.
- Missing weekly/daily candle data in confluence score (must handle missing data gracefully with partial score).
- Divergence detected in neutral 45-55 RSI chop without real momentum divergence (filter by minimum swing threshold).

---

### Task 1: Fibonacci Retracement & Extension Engine

**Files:**
- Modify: `trader-exit/exit_indian.py`
- Create: `tests/test_fibonacci_indian.py`

**Interfaces:**
- Produces: `calculate_fibonacci_levels(swing_high: float, swing_low: float, point_c: float = None) -> dict`

- [ ] **Step 1: Write failing unit tests for Fibonacci calculator**

Create `tests/test_fibonacci_indian.py` testing:
1. Retracements: swing high 2000, swing low 1000 (diff = 1000).
   - 23.6% = 1764.0
   - 38.2% = 1618.0
   - 50.0% = 1500.0
   - 61.8% = 1382.0
   - 78.6% = 1214.0
2. Extensions (point_c = 1400):
   - 127.2% = 1400 + 1000 * 1.272 = 2672.0
   - 161.8% = 1400 + 1000 * 1.618 = 3018.0
3. Integration with `plan_exit`: Passing `--fib-high 2000 --fib-low 1000` populates `fibonacci` levels in plan.
4. Validation: `swing_high <= swing_low` raises ValueError.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_fibonacci_indian.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `calculate_fibonacci_levels` in `trader-exit/exit_indian.py`**

- Implement `calculate_fibonacci_levels`:
  - Retracement levels: 23.6%, 38.2%, 50.0%, 61.8%, 78.6%.
  - Extension levels: 100.0%, 127.2%, 161.8%, 200.0%, 261.8%.
- Update `plan_exit` to accept `fib_high`, `fib_low`, `fib_c` and include `fibonacci` block.
- Add CLI arguments: `--fib-high`, `--fib-low`, `--fib-c`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests/test_fibonacci_indian.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git -C /Users/fahimahmad/comp/day-trader-skill add trader-exit/exit_indian.py tests/test_fibonacci_indian.py
git -C /Users/fahimahmad/comp/day-trader-skill commit -m "feat(exit): add Fibonacci retracement and extension calculation engine"
```

---

### Task 2: Regular & Hidden RSI Divergence Engine

**Files:**
- Modify: `trader-scanner/scan_indian.py`
- Create: `tests/test_divergence_indian.py`

**Interfaces:**
- Produces: `detect_rsi_divergences(closes: list, rsis: list = None, lookback: int = 30) -> list`

- [ ] **Step 1: Write failing unit tests for RSI divergence detection**

Create `tests/test_divergence_indian.py` testing:
1. Regular Bullish Divergence: Price Lower Low (100 -> 90) with RSI Higher Low (25 -> 32) -> flagged as `bullish_regular_divergence`.
2. Hidden Bullish Divergence: Price Higher Low (90 -> 95) with RSI Lower Low (38 -> 30) -> flagged as `bullish_hidden_divergence`.
3. Regular Bearish Divergence: Price Higher High (150 -> 160) with RSI Lower High (75 -> 68) -> flagged as `bearish_regular_divergence`.
4. Empty / insufficient data (< 20 points) returns empty list safely.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_divergence_indian.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `detect_rsi_divergences` in `trader-scanner/scan_indian.py`**

- Compute rolling 14-period RSI series if not passed.
- Extract swing lows and swing highs across the series.
- Detect slope discrepancies between price swing extrema and RSI swing extrema.
- Integrate divergence scan into `scan_daily_setups()`.
- Add CLI flag `--divergence`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests/test_divergence_indian.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git -C /Users/fahimahmad/comp/day-trader-skill add trader-scanner/scan_indian.py tests/test_divergence_indian.py
git -C /Users/fahimahmad/comp/day-trader-skill commit -m "feat(scanner): add regular and hidden RSI divergence detection engine"
```

---

### Task 3: 3-Screen Multi-Timeframe 6-Point Confluence Scoring

**Files:**
- Modify: `trader-entry/entry_indian.py`
- Modify: `trader-analyst/technical_analysis_indian.py`
- Create: `tests/test_confluence_indian.py`

**Interfaces:**
- Produces: `evaluate_3screen_confluence(symbol: str, weekly_candles: list, daily_candles: list, intraday_bars: list = None) -> dict`

- [ ] **Step 1: Write failing unit tests for confluence scoring**

Create `tests/test_confluence_indian.py` testing:
1. 6/6 points: All screens aligned -> Score 6, Rating `STRONG_CONFLUENCE`, Recommendation `FULL_SIZE`.
2. 3/6 points: Marginal alignment -> Score 3, Rating `MARGINAL_CONFLUENCE`, Recommendation `HALF_SIZE`.
3. 1/6 points: Weak alignment -> Score 1, Rating `WEAK_NO_TRADE`, Recommendation `SKIP`.
4. Missing weekly data handled gracefully without crash.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests/test_confluence_indian.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `evaluate_3screen_confluence`**

- Screen 1: Weekly trend (Price > 20W SMA, Weekly RSI > 50).
- Screen 2: Daily setup (Pattern, Daily RSI, Daily MACD/MA, S/R validation).
- Screen 3: Entry timing & volume (> 1.5x 20-DMA volume).
- Generate score (0-6), rating, and position size multiplier (1.0, 0.5, 0.0).
- Expose via CLI in `entry_indian.py --confluence`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m unittest tests/test_confluence_indian.py -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git -C /Users/fahimahmad/comp/day-trader-skill add trader-entry/entry_indian.py trader-analyst/technical_analysis_indian.py tests/test_confluence_indian.py
git -C /Users/fahimahmad/comp/day-trader-skill commit -m "feat(entry): add 3-screen multi-timeframe 6-point confluence scoring system"
```

---

### Task 4: Documentation & Integration

**Files:**
- Modify: `trader-scanner/SKILL.md`
- Modify: `trader-exit/SKILL.md`
- Modify: `trader-entry/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Update manuals and examples**
- [ ] **Step 2: Run all Indian market test suites**
- [ ] **Step 3: Commit documentation updates**
