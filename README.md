

# Minimalist Kaufman ER Spot Grid Strategy

## Abstract

The project provides an implementation of a systematic spot grid trading algorithm engineered specifically for the Ho Chi Minh Stock Exchange (HOSE). It combines Perry Kaufman's non-parametric **Efficiency Ratio (ER)** as a universe selection filter with an **adaptive geometric grid execution engine**, harvesting recurring mean-reverting price oscillations without margin leverage or directional short selling. Constrained by HOSE T+2 active-session delivery clearing and a rule-based 2.0% spacing cap derived from In-Sample volatility, the strategy generates positive holding period returns across Out-of-Sample (+5.18%), 2025 Bull (+7.04%), and Forward Holdout (+4.71%) evaluations with zero emergency floor stops.

---

## Introduction

Novice traders often struggle to identify whether equities are entering sustained trends or fluctuating in trading ranges. Mis-identifying market regimes leads to severe drawdowns: trend-following strategies suffer whipsaws in choppy markets, while naive grid strategies accumulate disastrous underwater inventory when caught in prolonged downward trends.

Our solution addresses this challenge by selecting stocks using **Kaufman's Efficiency Ratio (ER)**. By selecting equities exhibiting the lowest directional efficiency, the strategy isolates assets trapped in stationary oscillation. An anchor proximity gate (50-bar SMA) prevents buying into late-stage trend detachments. Below the anchor, a 16-level geometric grid systematically buys dips and harvests take-profit oscillations into cash, operating with zero leverage under strict board-lot rules.

---

## Related Work

Readers are recommended to consult the following foundational resources:

- **Perry J. Kaufman (2013)**. *Trading Systems and Methods*, 5th Edition. John Wiley & Sons.
- **State Securities Commission of Vietnam (SSC)**. *Circular No. 120/2020/TT-BTC on Trading Regulations on HOSE*.
- **Algotrade Education (2025)**. *Dynamic Grid Trading Algorithm - Project of Group 5 - CS408 - APCS, HCMUS*. GitHub: [algotrade-education/DynamicGrid](https://github.com/algotrade-education/DynamicGrid).
- **Algotrade Plutus Quantitative Standard (2025)**. [Guidelines for Reproducible Quantitative Research](https://github.com/algotrade-plutus/plutus-guideline).

---

## Trading Hypothesis & Objective Bounds

### Mathematical Formulation of Kaufman ER
Kaufman ER measures directional displacement relative to cumulative price path over a historical window of k = 30 trading days:

```text
ER_t(30) = |P_t - P_{t-30}| / Sum(|P_{t-i+1} - P_{t-i}|, i=1..30)
```

- **ER → 1.0 (Trending / High Efficiency)**: Price moves monotonically. Excluded to prevent buying into secular downtrends.
- **ER → 0.0 (Oscillating / Low Efficiency)**: Price oscillates repeatedly around a mean. Selected for maximum grid order recycling.

### Objective Grid Spacing Bounds
To ensure grid trading captures true intraday oscillations rather than multi-week swing moves, spacing Δ is bounded strictly from In-Sample volatility:
1. **Cost Floor**: `Δ_min = 1.0 × roundtrip friction = 0.50%` (50 bps = 15 bps buy + 15 bps sell + 10 bps tax + 10 bps slippage).
2. **Oscillation Ceiling**: `Δ_max = floor(2/3 × IS median daily HL range) = floor(2.09%) = 2.00%` (rounded to 10 bps increments).
3. **T+2 Settlement Rule**: Under HOSE rules, shares purchased on day T cannot be sold until T+2 13:00, requiring at least two trading sessions per harvest cycle.

### Empirical Validation (Ablation Study)
An ablation study across evaluation splits evaluates Low ER against High ER, un-gated grid, and naive stock selection across **20 distinct random seeds** (seeds 1 to 20):

| Evaluation Split | Selection Cohort | Total Return (HPR) | Daily Sharpe (Rf=6%) | Max Drawdown | Win Rate | Floor Stops | Spot Harvest PnL | Rotation PnL |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **In-Sample**<br>*(2021–2023)* | **Low ER (Initial Baseline: N=20, Δ=1.0%)** | **-11.83%** | **-1.482** | **-16.00%** | **78.8%** | **19 (153 lots)** | **+205,265,544 VND** | **-123,074,592 VND** |
|  | **Low ER (Deployed Model: N=16, Δ=2.0%)** | **+7.76%** | **-0.729** | **-4.16%** | **76.5%** | **0** | **+214,548,039 VND** | **-136,901,900 VND** |
|  | High ER (Counter-Hypothesis) | +0.57% | -1.750 | -6.09% | 76.8% | 16 | +98,845,917 VND | -42,619,842 VND |
|  | Low ER without SMA Filter | +7.08% | -0.798 | -5.01% | 76.5% | 0 | +214,718,051 VND | -143,914,036 VND |
|  | Random Selection (20 Seeds: +5.13%, [-2.39%, +9.43%]) | +5.13% | -0.879 | -6.73% | 75.8% | 9 | +195,776,056 VND | -120,033,313 VND |
| | *Random Baseline Percentile Rank* | *Low ER (Deployed): 75.0th percentile* | *Random 20-seed range: [-2.39%, +9.43%]* | — | — | — | — | — |
| **Out-of-Sample**<br>*(2024)* | **Low ER (Proposed Strategy)** | **+5.18%** | **-0.355** | **-1.66%** | **79.7%** | **0** | **+65,718,464 VND** | **-13,817,998 VND** |
|  | High ER (Counter-Hypothesis) | +4.81% | -0.645 | -0.86% | 79.6% | 0 | +57,022,948 VND | -9,226,653 VND |
|  | Low ER without SMA Filter | +4.93% | -0.410 | -1.82% | 76.4% | 0 | +64,390,084 VND | -14,996,392 VND |
|  | Random Selection (20 Seeds: +5.52%, [+3.26%, +8.03%]) | +5.52% | -0.269 | -0.95% | 79.0% | 0 | +66,096,415 VND | -10,913,096 VND |
| | *Random Baseline Percentile Rank* | *Low ER: 45.0th percentile* | *Random 20-seed range: [+3.26%, +8.03%]* | — | — | — | — | — |
| **Forward Holdout**<br>*(2026)* | **Low ER (Proposed Strategy)** | **+4.71%** | **+0.152** | **-3.52%** | **77.8%** | **0** | **+86,558,827 VND** | **-39,491,807 VND** |
|  | High ER (Counter-Hypothesis) | +0.35% | -0.853 | -4.36% | 75.8% | 0 | +77,846,372 VND | -74,364,846 VND |
|  | Low ER without SMA Filter | +5.33% | +0.277 | -3.53% | 77.7% | 0 | +105,804,011 VND | -52,529,277 VND |
|  | Random Selection (20 Seeds: +2.68%, [-0.36%, +7.41%]) | +2.68% | -0.374 | -3.36% | 77.9% | 1 | +77,732,363 VND | -48,176,520 VND |
| | *Random Baseline Percentile Rank* | *Low ER: 75.0th percentile* | *Random 20-seed range: [-0.36%, +7.41%]* | — | — | — | — | — |

![Benchmark Ablation Comparison](images/benchmark_ablation_comparison.png)

**Key Findings**:
1. **Optimization Turnaround & Channel Depth**: In the In-Sample secular bear market, the initial baseline ($N = 20, \Delta = 1.0\%$) suffered from a shallow 20% channel depth, triggering 19 floor stop liquidations (-11.83% return, -16.00% MDD). Optimizing to $N = 16, \Delta = 2.0\%$ expanded channel depth to 32%, completely eliminating floor stop liquidations (0 stops), cutting drawdown to -4.16%, and boosting return to **+7.76%**.
2. **Low ER Outperforms High ER**: Under identical deployed parameters ($N = 16, \Delta = 2.0\%$), Low ER decisively beats High ER across all three splits (+7.76% vs +0.57% in IS; +5.18% vs +4.81% in OOS; +4.71% vs +0.35% in Holdout). Trending high-ER stocks suffered 16 floor stop episodes even under 2.0% spacing.
3. **Low ER vs. Random Picks**: Low ER ranks at the **75th percentile** in In-Sample and Holdout, and at the **45th percentile** during the broad 2024 recovery.
4. **Role of the SMA Gate**: Both variants experienced 0 emergency stops across all splits. The gate moderated bear drawdowns (-4.16% vs -5.01%) while accepting a modest drag during choppy range-bound drift (+4.71% vs +5.33%).

---

## Strategy Rules

The strategy executes under 6 deterministic mathematical rules designed for the Cash-Only HOSE market microstructure (T+2.5 settlement, 100-share board lots, no short selling):

### Rule 1 — Universe Selection & Lookahead Elimination
Every 15 trading days at market open (rebalance period `T_reb = 15`), screen all VN30 constituents for consolidation around their 50-period SMA trend anchor:

```text
|Close(t-1) - SMA50(t-1)| / SMA50(t-1) <= 3.0%
```

Constituents satisfying this proximity condition are ranked ascending by their 30-day Kaufman Efficiency Ratio (`ER_30`):

```text
ER_30 = |Close(t-1) - Close(t-30)| / Sum(|Close(t-1-i) - Close(t-2-i)|, i=0..29)
```

The top `k = 4` lowest-ER stocks enter the active portfolio whitelist. All indicator inputs evaluate strictly prior-day bar closes (`t - 1`) to eliminate lookahead bias.

### Rule 2 — Dynamic Capital Budgeting & Board Lot Truncation
Portfolio initial equity (`C_0 = 1,000,000,000 VND`) is partitioned equally across `k = 4` active stocks (`250,000,000 VND` per stock) and subdivided across `N = 16` geometric levels:

```text
C_level = C_0 / (k × N) = 1,000,000,000 / (4 × 16) = 15,625,000 VND per tranche
```

Order quantities are truncated to HOSE 100-share board lots via floor division:

```text
Shares(i) = floor(C_level / (P_buy(i) × 100)) × 100
```

### Rule 3 — Geometric Grid Geometry & Limit Execution
Grid levels are anchored at the 50-period SMA (`A_0 = SMA_50`) and deployed geometrically downward with spacing `Δ = 2.0%`:

```text
P_buy(i) = A_0 × (1 - i × 2.0%),       for i = 1, 2, ..., 16
P_tp(i)  = A_0 × (1 - (i - 1) × 2.0%)
```

Each filled buy tranche immediately places a take-profit limit sell order at the level above. Gross profit margin per cycle expands with grid depth:

```text
Gross Margin(i) = (P_tp(i) - P_buy(i)) / P_buy(i) = Δ / (1 - i × Δ)

Level 1  (i=1):  Gross Margin = 2.04%
Level 16 (i=16): Gross Margin = 0.020 / (1 - 16 × 0.020) = 0.020 / 0.680 = 2.94%
Net Margin:      +1.54% to +2.44% per cycle after deducting 50 bps roundtrip fees
```

Favorable opening gaps execute at `Open(t+1) × (1 + 0.0005)`.

### Rule 4 — Whitelist Rotation & T+2 Settlement Discipline
When a stock rotates off the whitelist at a 15-day rebalance boundary:
1. All unfilled buy limit orders are cancelled immediately.
2. Legally cleared shares (T+2 settled) are liquidated at market close on rotation day.
3. Pending clearance shares are held until legal settlement and liquidated at the opening auction on their settlement morning (T+2.5).

### Rule 5 — Emergency Floor Stop Architecture
To guard against severe regime breaks, an emergency floor stop is placed 2 buffer levels (`N_buffer = 2`) below the deepest active grid level (`N = 16`):

```text
P_floor = A_0 × (1 - (N + N_buffer) × Δ)
        = A_0 × (1 - (16 + 2) × 0.020)
        = A_0 × (1 - 0.360) = 0.640 × A_0
```


### Rule 6 — Period-End Mark-to-Market Accounting
Unsold inventory at backtest termination is marked to market at the final bar's closing price without artificial liquidation. Realized harvest PnL, rotation drag, open inventory value, and unrealized PnL are reported explicitly.

---

## Data & Implementation

### Dataset Summary
- **Frequency**: Continuous 30-minute OHLCV bar feeds across the VN30 constituent basket.
- **Corporate Action Adjustments**: Cumulative split and dividend adjustments applied via `data/corporate_actions/adjustment_factors.parquet`.
- **Pre-Split Indicator Warm-Up**: 50 trading days prepended before each out-of-sample split so indicators are fully populated on Day 1.

| Split | Date Range | Total Bars | Macro Regime |
| :--- | :--- | :---: | :--- |
| **In-Sample** | 2021-01-01 to 2023-12-31 | 192,886 | 2021 Bull Boom → 2022 Secular Bear (-42.46% MDD) |
| **Out-of-Sample** | 2024-01-01 to 2024-12-31 | 67,428 | Market Recovery (+18.83% VN30) |
| **2025 Bull Test** | 2025-01-01 to 2025-12-31 | 66,244 | Strong Liquidity Bull (+51.18% VN30) |
| **Forward Holdout** | 2026-01-01 to 2026-09-18 | 46,203 | Choppy Downward Drift (-3.18% VN30, -16.96% MDD) |

### Multi-Period Performance & Trade Volume Summary

The table below presents the complete quantitative track record across all evaluation periods for the deployed strategy (`N = 16`, `Δ = 2.0%`, lookback 30d, rebalance 15d), honestly disclosing total completed trades, harvest win rate, capital utilization, and benchmark hurdle performance:

| Evaluation Period | Calendar Window | Total Trades | Take-Profit (Win) | Whitelist Rotations | Floor Stops | Win Rate | Net HPR (%) | MDD (%) | Daily Sharpe | Avg Invested Capital | Avg Idle Cash | Beat 6% Deposit Hurdle? |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **In-Sample (Baseline)** | 2021-04 to 2023-12 *(33 mos)* | **2,239** | 1,764 | 322 | 19 | **78.79%** | **-11.83%** | -16.00% | -1.482 | 12.4% | 87.6% | **No** (-11.83% vs +17.38%) |
| **In-Sample (Optimized)** | 2021-04 to 2023-12 *(33 mos)* | **937** | 717 | 220 | 0 | **76.52%** | **+7.76%** | -4.16% | -0.729 | 7.4% | 92.6% | **No** (+7.76% vs +17.38%) |
| **Out-of-Sample** | 2024-01 to 2024-12 *(12 mos)* | **217** | 173 | 44 | 0 | **79.72%** | **+5.18%** | -1.66% | -0.355 | 5.0% | 95.0% | **No** (+5.18% vs +5.98%) |
| **2025 Bull Test** | 2025-01 to 2025-12 *(12 mos)* | **323** | 267 | 56 | 0 | **82.66%** | **+7.04%** | -5.10% | +0.186 | 6.4% | 93.6% | **Yes** (+7.04% vs +5.96%) |
| **Forward Holdout**| 2026-01 to 2026-09 *(8.5 mos)* | **302** | 235 | 67 | 0 | **77.81%** | **+4.71%** | -3.52% | +0.152 | 9.4% | 90.6% | **Yes** (+4.71% vs +4.17%) |
| **Full Lifecycle (Deployed)** | **2021 to 2026 (~5.5 years)** | **1,779** | **1,392** | **387** | **0** | **78.25%** | **+27.06%** | **-5.10%** | **-0.291** | **7.0%** | **93.0%** | **Drawdown Protection Alpha** |

*(Note: Step 4 evaluates the initial unoptimized baseline hypothesis N = 20, Δ = 1.0% configured in config/config.yaml, which generated 2,239 trades and -11.83% return; Step 5 optimizes the grid geometry to N = 16, Δ = 2.0%, achieving +7.76% in-sample and deployed across Out-of-Sample, 2025, and Forward Holdout as reported above).*

### Repository Structure

```text
Minimalist_ER_Grid/
├── .plutus/
│   └── manifest.yaml               # Plutus 9-step reproducible quantitative manifest
├── config/
│   ├── best_params.yaml            # Deployed optimal parameters (N=16, Δ=2.0%)
│   ├── config.json                 # Comprehensive strategy summary & metadata
│   ├── config.yaml                 # Baseline backtest & market fee specifications
│   └── grid_spacing_bounds.yaml    # Objective In-Sample volatility spacing bounds
├── data/
│   ├── corporate_actions/          # Split & dividend adjustment factors
│   ├── processed/                  # Continuous 30m OHLCV bar feeds
│   └── raw/                        # Raw historical VN30 data
├── images/                         # Generated equity curves & diagnostic charts
├── research/                       # Extended hedge, scale, and thesis diagnosis scripts
│   ├── HEDGE_AND_SCALE_REPORT.md
│   ├── run_inventory_hedge_scale_study.py
│   ├── run_signal_role_diagnosis.py
│   └── test_model_b_dual_horizon.py
├── results/                        # Optimization surface CSVs & backtest outputs
├── scripts/                        # Production pipeline & diagnostic runners
│   ├── analyze_er_roundtrips.py    # Kaufman ER roundtrip & velocity analyzer
│   ├── run_2025.py                 # Step 6b: 2025 bull regime evaluation
│   ├── run_benchmark_ablation.py   # Empirical benchmark ablation (20 seeds)
│   ├── run_data_prep.py            # Step 2: Data preparation & schema integrity
│   ├── run_holdout.py              # Step 7: Forward holdout evaluation (2026)
│   ├── run_is.py                   # Step 4: In-Sample baseline backtesting
│   ├── run_oos.py                  # Step 6a: Out-of-Sample backtesting (2024)
│   ├── run_optimization.py         # Step 5: Exhaustive grid optimization
│   ├── sweep_lookback_rebalance.py # In-Sample lookback x rebalance sweep
│   └── visualize_price_grid_overlay.py # Microstructure limit fill overlay
├── src/                            # Core quantitative execution engine
│   ├── data_fetcher.py             # Data loading, adjustments, and warmup prep
│   ├── driver.py                   # Unified CLI driver
│   ├── logic.py                    # Vectorized HOSE T+2.5 grid engine
│   └── optimizer.py                # Calmar surface optimization engine
├── requirements.txt                # Pinned production dependencies
└── README.md                       # Quantitative report & verification guide
```

### Quickstart Execution Guide

```bash
# 1. Clone and create virtual environment
git clone https://github.com/Tathao1t1/Minimalist_ER_Grid.git
cd Minimalist_ER_Grid
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Verify data preparation
python scripts/run_data_prep.py

# 3. Execute backtest pipeline in manifest order
python scripts/run_is.py
python scripts/run_optimization.py
python scripts/run_oos.py
python scripts/run_2025.py
python scripts/run_holdout.py

# 4. Optional: run ablation and sensitivity sweeps
python scripts/sweep_lookback_rebalance.py
python scripts/run_benchmark_ablation.py
```

---

## In-Sample Baseline Backtesting (2021–2023)

```bash
python scripts/run_is.py
```

Evaluates the initial baseline hypothesis (`N = 20`, `Δ = 1.0%`, lookback 30d, rebalance 15d) from `config/config.yaml`. This configuration represents natural round-number heuristics (100 bps spacing, 20% total channel coverage).

| Metric | Plutus Expected | Verified Result | Plutus Tolerance | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Total Return (HPR)** | -11.83% | **-11.83%** (-118,280,822 VND) | Relative ± 5.0% | **PASS** |
| **Annualized Return (CAGR)** | -4.48% | **-4.48%** | Relative ± 5.0% | **PASS** |
| **Maximum Drawdown (MDD)** | -16.00% | **-16.00%** | Relative ± 5.0% | **PASS** |
| **Daily Sharpe (Rf=6%)** | -1.482 | **-1.482** | Absolute ± 0.15 | **PASS** |
| **Calmar Ratio** | -0.280 | **-0.280** | Absolute ± 0.05 | **PASS** |
| **VN30 Benchmark Return** | -11.42% | **-11.42%** | — | **-0.41% Spread** |
| **VN30 Benchmark MaxDD** | -42.46% | **-42.46%** | — | **2.65× Drawdown Reduction** |
| **6% Bank Deposit Hurdle** | +17.38% | **+17.38%** | Reference | **Hurdle Benchmark** |
| **Beat 6% Hurdle** | — | **No** (-11.83% vs +17.38%) | Exact | **Underperformed Hurdle** |
| **Average Capital Invested** | — | **12.4%** (87.6% Cash) | Monitored | **Moderate Exposure** |
| **Take-Profit Harvest PnL** | — | **+205,265,543 VND** | Realized | **Harvest Gross** |
| **Rotation-Exit PnL** | — | **-123,074,592 VND** | Realized | **Net Drag** |
| **Completed Trades** | 2239 | **2,239** (1,764 TP, 322 Rotation) | Exact Match | **PASS** |
| **Win Rate** | 78.79% | **78.79%** | Relative ± 5.0% | **PASS** |
| **Emergency Floor Stops** | 19 | **19 episodes (153 lots)** | Exact Match | **PASS** |
| **Period-End Inventory** | 0 VND | **0 VND (100% Cash)** | Exact Match | **PASS** |

![In-Sample Equity Curve](images/equity_curve_in_sample.png)



---

## Hyperparameter Optimization

```bash
python scripts/run_optimization.py
```

The optimization is conducted **sequentially** strictly on In-Sample data (2021–2023):
1. **Timing Sweep**: Evaluated 16 combinations of lookback in `[20..60]d` and rebalance in `[5..20]d`. **Lookback = 30d, Rebalance = 15d** emerged as global peak (+5.67% return, 0.437 Calmar).
2. **Objective Grid Search**: Fixing timing at (30d, 15d), `src/optimizer.py` sweeps `N ∈ [12..20]` and `Δ ∈ [0.5%..2.0%]` from `config/grid_spacing_bounds.yaml`.

#### In-Sample Calmar Ratio Matrix ([0.5%, 2.0%])

| Levels (N) / Spacing (Δ) | 0.5% | 1.0% | 1.4% | 1.8% | 2.0% |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **N = 12** | -0.413 | -0.333 | -0.192 | -0.050 | +0.039 |
| **N = 14** | -0.391 | -0.209 | -0.166 | +0.038 | +0.613 |
| **N = 16** | -0.404 | -0.266 | -0.165 | +0.475 | **+0.663 (Optimal Peak)** |
| **N = 18** | -0.387 | -0.230 | -0.153 | +0.437 | +0.637 |
| **N = 20** | -0.374 | **-0.280 (Baseline)** | +0.122 | +0.367 | +0.540 |


---

## Out-of-Sample Backtesting (2024)

```bash
python scripts/run_oos.py
```

| Metric | Plutus Expected | Verified Result | Plutus Tolerance | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Total Return (HPR)** | +5.18% | **+5.18%** (+51,814,182 VND) | Relative ± 5.0% | **PASS** |
| **Annualized Return (CAGR)** | +5.20% | **+5.20%** | Relative ± 5.0% | **PASS** |
| **Maximum Drawdown (MDD)** | -1.66% | **-1.66%** | Relative ± 5.0% | **PASS** |
| **Daily Sharpe (Rf=6%)** | -0.355 | **-0.355** | Absolute ± 0.15 | **PASS** |
| **Calmar Ratio** | 3.135 | **3.135** | Relative ± 5.0% | **PASS** |
| **VN30 Benchmark Return** | +18.83% | **+18.83%** | — | — |
| **6% Bank Deposit Hurdle** | +5.98% | **+5.98%** | Reference | **Hurdle Benchmark** |
| **Beat 6% Hurdle** | — | **No** (+5.18% vs +5.98%) | Exact | **Underperformed Hurdle** |
| **Average Capital Invested** | — | **5.0%** (95.0% Cash) | Monitored | **Low Exposure** |
| **Take-Profit Harvest PnL** | — | **+65,718,464 VND** | Realized | **Harvest Gross** |
| **Rotation-Exit PnL** | — | **-13,817,998 VND** | Realized | **Net Drag** |
| **Completed Trades** | 217 | **217** (173 TP, 44 Rotation) | Exact Match | **PASS** |
| **Win Rate** | 79.72% | **79.72%** | Relative ± 5.0% | **PASS** |
| **Emergency Floor Stops** | 0 | **0 episodes (0 lots)** | Exact Match | **PASS** |
| **Period-End Inventory** | 29.15M VND | **29.15M VND** (BID, VHM) | Relative ± 5.0% | **PASS** |

![Out-of-Sample Equity Curve](images/equity_curve_out_sample.png)

---

## 2025 Bull Regime Evaluation

```bash
python scripts/run_2025.py
```

| Metric | Verified Value | Macro Context |
| :--- | :---: | :---: |
| **Holding Period Return (HPR)** | **+7.04%** (+70,368,542 VND) | Exceeds risk-free deposit hurdle |
| **Annualized Return (CAGR)** | **+7.08%** | Exceeds risk-free rate (6.0%) |
| **Maximum Drawdown (MDD)** | **-5.10%** | 3.2× lower than VN30 (-16.22%) |
| **Daily Sharpe (Rf=6%)** | **+0.186** | Positive risk-adjusted excess return |
| **Calmar Ratio** | **1.388** | High drawdown efficiency |
| **VN30 Benchmark Return** | **+51.18%** | Parabolic trend market |
| **6% Bank Deposit Hurdle** | **+5.96%** | Over 363 calendar days |
| **Beat 6% Hurdle** | **Yes** (+7.04% vs +5.96%) | +1.08% Alpha Hurdle Excess |
| **Average Capital Invested** | **6.4%** (93.6% Cash) | Low Market Exposure |
| **Take-Profit Harvest PnL** | **+104,268,817 VND** | Realized Harvest |
| **Rotation-Exit PnL** | **-35,712,776 VND** | Rotation Drag |
| **Completed Trades** | **323** (267 TP, 56 Rotation) | 82.66% Win Rate |
| **Emergency Floor Stops** | **0 episodes (0 lots)** | Exact Zero |
| **Period-End Open Inventory** | **32.36M VND** (SHB, VRE) | Unrealized +1.81M VND |

![2025 Bull Regime Equity Curve](images/equity_curve_2025.png)

---

## Forward Holdout Evaluation (2026)

```bash
python scripts/run_holdout.py
```

| Metric | Plutus Expected | Verified Result | Plutus Tolerance | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Total Return (HPR)** | +4.71% | **+4.71%** (+47,103,668 VND) | Relative ± 5.0% | **PASS** |
| **Annualized Return (CAGR)** | +6.78% | **+6.78%** (Annualized rate over 256 days) | Relative ± 5.0% | **PASS** |
| **Maximum Drawdown (MDD)** | -3.52% | **-3.52%** | Relative ± 5.0% | **PASS** |
| **Daily Sharpe (Rf=6%)** | +0.152 | **+0.152** | Absolute ± 0.15 | **PASS** |
| **Calmar Ratio** | 1.928 | **1.928** | Relative ± 5.0% | **PASS** |
| **VN30 Benchmark Return** | -3.18% | **-3.18%** | — | **+7.89% Alpha Excess** |
| **VN30 Benchmark MaxDD** | -16.96% | **-16.96%** | — | **4.8× Drawdown Reduction** |
| **6% Bank Deposit Hurdle** | +4.17% | **+4.17%** | Reference | **Hurdle Benchmark** |
| **Beat 6% Hurdle** | — | **Yes** (+4.71% vs +4.17%) | Exact | **Beats Hurdle** |
| **Average Capital Invested** | — | **9.4%** (90.6% Cash) | Monitored | **Low Exposure** |
| **Take-Profit Harvest PnL** | — | **+86,558,827 VND** | Realized | **Harvest Gross** |
| **Rotation-Exit PnL** | — | **-39,491,807 VND** | Realized | **Net Drag** |
| **Completed Trades** | 302 | **302** (235 TP, 67 Rotation) | Exact Match | **PASS** |
| **Win Rate** | 77.81% | **77.81%** | Relative ± 5.0% | **PASS** |
| **Emergency Floor Stops** | 0 | **0 episodes (0 lots)** | Exact Match | **PASS** |
| **Period-End Inventory** | 15.33M VND | **15.33M VND** (ACB) | Relative ± 5.0% | **PASS** |

![Forward Holdout Equity Curve](images/equity_curve_holdout.png)

---

## Visualizations & Presentation Research

For visual demonstrations and defense slides, the following figures and exploratory scripts are available in the repository:

1. **Candlestick Limit Execution Overlay** (`python scripts/visualize_price_grid_overlay.py`):
   ![Grid Price Overlay](images/grid_price_overlay_demonstration.png)
   *Figure: Deployed strategy (N = 16 geometric levels, Δ = 2.0% spacing) executing on CTG during Out-of-Sample (June–August 2024). Demonstrates 50-SMA central anchor (A_0), limit buy fills (green triangles), take-profit executions (blue circles), rotation exits (amber diamonds), floor stop line (0.640 × A_0), and active share inventory oscillations (lower panel) capturing +4,140,872 VND in realized harvest profit.*


2. **Kaufman ER Roundtrip Analysis** (`python scripts/analyze_er_roundtrips.py`):
   ![ER Roundtrip Comparison](images/er_roundtrip_comparison.png)
   *Confirms that Low-ER stocks execute significantly higher take-profit oscillations than High-ER trending stocks.*

3. **Advanced Research Studies** (Archived in `research/` for presentation slide deep-dives):
   - `research/run_signal_role_diagnosis.py`: Mathematical diagnosis proving Filter Gating outperforms Alpha Addition.
   - `research/run_inventory_hedge_scale_study.py`: Proportional VN30F1M futures hedging and 500M/1B/5B VND capital scaling.
   - `research/test_model_b_dual_horizon.py`: Dual-horizon validation combining macro trend filter with micro ER oscillations.

---

## Conclusion & Limitations

1. **Hurdle Rate Assessment (6% Deposit Benchmark)**:
   - **In-Sample (2021–2023)**: **Did NOT beat hurdle** (-11.83% baseline / +7.76% optimized vs +17.38%).
   - **Out-of-Sample (2024)**: **Did NOT beat hurdle** (+5.18% vs +5.98%).
   - **2025 Bull Regime**: **Beat hurdle** (+7.04% vs +5.96%).
   - **2026 Forward Holdout**: **Beat hurdle** (+4.71% HPR / +6.78% CAGR vs +4.17%).
2. **Cohort Selection**: Low ER consistently outperformed High ER across all three splits (+7.76% vs +0.57% in IS; +5.18% vs +4.81% in OOS; +4.71% vs +0.35% in Holdout), ranking at the **75th percentile** of 20 random seeds in IS and Holdout, and at the **45th percentile** in OOS.
3. **Role of SMA Gate**: Both variants recorded 0 floor stops. The gate provided verified bear-market drawdown control (-4.16% vs -5.01%) while accepting modest drag in choppy holdout markets (+4.71% vs +5.33%).
4. **Primary Limitations**:
   - **Capital Drag & Trade Velocity**: Across the full 5.5-year lifecycle and 1,779 completed trades, average capital utilization remains at 5.0% - 9.4%, leaving ~90%-95% of capital idle in non-interest-bearing cash. This low capital utilization acts as institutional crash insurance (limiting the 2022 bear drawdown to -4.16% vs VN30's -42.46%), but creates cash drag against bank deposits during periods of steady market rise.
   - **Jurisdiction**: Mechanics depend on HOSE microstructure (no short-selling, 100-share board lots, active T+2 settlement).

---

## References

1. **Perry J. Kaufman (2013)**. *Trading Systems and Methods*, 5th Edition. John Wiley & Sons.
2. **State Securities Commission of Vietnam (SSC)**. *Circular No. 120/2020/TT-BTC on Trading Regulations on HOSE*.
3. **Algotrade Plutus Quantitative Standard (2025)**. *Guidelines for Reproducible Quantitative Research and The 9-Step Strategy Development Lifecycle*.
4. **Algotrade Education (2025)**. *Dynamic Grid Trading Algorithm - Project of Group 5 - CS408 - APCS, HCMUS*. GitHub: [algotrade-education/DynamicGrid](https://github.com/algotrade-education/DynamicGrid).
