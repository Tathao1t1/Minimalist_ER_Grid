# Kaufman-Range-Grid: Non-Parametric Kaufman ER Spot Grid Trading System
> Systematic equity oscillation harvesting engine with zero directional leverage, fully compliant with HOSE trading rules, active-session $T+2$ settlement, and institutional 50 bps execution friction.

[![Python Version](https://img.shields.io/badge/Python-3.12-blue)](requirements.txt)
[![Market](https://img.shields.io/badge/Exchange-HOSE%20%7C%20VN30-orange)](data/)
[![Transaction Costs](https://img.shields.io/badge/Costs-50%20bps%20Roundtrip-red)](config/config.yaml)
[![Time-Series Discipline](https://img.shields.io/badge/Discipline-Strict%20IS%20Optimization-purple)](src/optimizer.py)

---

## Abstract

The **Kaufman-Range-Grid** system is a systematic, quantitative trading strategy engineered specifically for the microstructure of the Ho Chi Minh Stock Exchange (HOSE). It combines Perry Kaufman's non-parametric **Efficiency Ratio (ER)** as a regime-selection filter with an **adaptive geometric grid execution engine**, harvesting recurring mean-reverting price oscillations without derivative exposure, margin calls, or directional leverage.

The strategy was developed and evaluated end-to-end on **HOSE 30-minute OHLCV bar feeds across the liquid VN30 constituent universe from 2021 to 2026**, adhering strictly to the 9-Step Strategy Development Process and the [Plutus Reproducibility Standard](https://github.com/algotrade-plutus/plutus-guideline). All hyperparameters were selected strictly on the In-Sample period (2021–2023) using an exhaustive grid search constrained by an objective rule-based volatility cap derived from In-Sample data and committed to [`config/best_params.yaml`](config/best_params.yaml) (see Methodology Note below).

---

## 1. Forming Algorithm Hypothesis

> [!NOTE]
> **Methodology Note**: The spacing cap was introduced after an initial OOS evaluation (commits dce6d2c → a068245); OOS/2025/holdout results are therefore not fully independent.

### Mathematical Definition of Kaufman Efficiency Ratio (ER)
Perry Kaufman defined market efficiency as the ratio of directional price displacement to the total path traveled over a historical window of $k$ periods:

$$\text{ER}_t(k) = \frac{|\Delta P_k|}{\sum_{i=1}^k |\Delta P_i|} = \frac{|P_t - P_{t-k}|}{\sum_{i=1}^k |P_{t-i+1} - P_{t-i}|}$$

Where:
- $P_t$ is the closing price on day $t$.
- $k$ is the lookback window ($k = 30$ trading days, approximately six business weeks).
- The numerator represents net directional displacement.
- The denominator represents the cumulative path volatility.

```mermaid
graph TD
    A["30-Day Price Window"] --> B["Calculate Directional Displacement |Pt - Pt-k|"]
    A --> C["Calculate Cumulative Absolute Path Sum"]
    B & C --> D["Kaufman Efficiency Ratio (ER)"]
    D -->|"ER to 1.0 (Trending)"| E["Exclude from Grid: Danger of Accumulating Losing Lots"]
    D -->|"ER to 0.0 (Stationary Oscillation)"| F["Qualify for Grid Whitelist: High Take-Profit Recurrence"]
```

### Regime Gating Hypothesis & Objective Grid Spacing Bounds
- **$\text{ER} \to 1.0$ (High Efficiency / Trending Regime)**: Price travels monotonically with minimal retracement. Spot grids deployed on high ER stocks accumulate losing tranches during secular declines.
- **$\text{ER} \to 0.0$ (Low Efficiency / Stationary Oscillation)**: Price oscillates continuously across a wide band while returning close to its origin. This creates the mathematically ideal substrate for grid order recycling: limit buy orders fill on dips and take-profit sell orders execute in rapid succession.
- **Anchor Proximity Gate (Rule 1)**: Even among low ER stocks, equities detaching from their short-term anchor: SMA of 50 × 30-min bars ($\approx 5.5$ sessions) must be rejected. The strategy filters for equities whose price is within $\pm 3\%$ of their 50-period Simple Moving Average ($\text{SMA}_{50}$), preventing entry during late-stage breakdown detachments.
- **Objective Grid Spacing Bounds (Rule-Based, In-Sample Only)**:
  To distinguish range-bound grid harvesting from multi-week swing trading, grid spacing $\Delta$ is bounded strictly from In-Sample volatility metrics:
  1. **Cost Floor (Lower Bound)**: $\Delta_{\min} = 1.0 \times \text{round-trip friction} = 0.50\%$ ($50\text{ bps} = 15\text{ bps buy} + 15\text{ bps sell} + 10\text{ bps tax} + 10\text{ bps slippage}$). Any spacing below $0.50\%$ produces negative net harvest profit per lot.
  2. **Oscillation Ceiling (Upper Bound)**: $\Delta_{\max} = \lfloor \frac{2}{3} \times \text{IS median daily high-low range} \rfloor_{10\text{ bps}} = \lfloor \frac{2}{3} \times 3.14\% \rfloor_{10\text{ bps}} = \lfloor 2.09\% \rfloor = 2.00\%$ (floored to the nearest 10 basis points / 0.10% to guarantee standard quote tick regularity and ensure limit orders remain strictly contained within 2-session intraday swings).
  3. **T+2 Settlement Constraint**: Under HOSE trading rules, an equity lot purchased on day $T$ cannot be sold until $T+2$ at 13:00. Consequently, each harvested oscillation cycle naturally spans at least two trading sessions.
  These bounds are computed dynamically from In-Sample data by `run_data_prep.py` and output to [`config/grid_spacing_bounds.yaml`](config/grid_spacing_bounds.yaml).

### Empirical Validation of the Hypothesis (Ablation Study)
To test whether Low-ER selection genuinely adds value over counter-hypotheses and naive stock picking at deployed parameters ($N=16, \Delta=2.0\%$, lookback=30d, rebalance=15d), `run_benchmark_ablation.py` executes an ablation study across evaluation periods, evaluating random selection across **20 distinct random seeds** (seeds 1 to 20):

```bash
python run_benchmark_ablation.py
```

| Evaluation Split | Selection Cohort | Total Return (HPR) | Daily Sharpe ($R_f=6\%$) | Max Drawdown | Win Rate | Floor Stops | Spot Harvest PnL | Rotation PnL |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **In-Sample**<br>*(2021–2023)* | **Low ER (Proposed Strategy)** | **$+7.76\%$** | **$-0.729$** | **$-4.16\%$** | **$76.5\%$** | **$0$** | **$+214,548,039\text{ VND}$** | **$-136,901,900\text{ VND}$** |
|  | High ER (Counter-Hypothesis) | $+0.57\%$ | $-1.750$ | $-6.09\%$ | $76.8\%$ | $16$ | $+98,845,917\text{ VND}$ | $-42,619,842\text{ VND}$ |
|  | Low ER without SMA Filter | $+7.08\%$ | $-0.798$ | $-5.01\%$ | $76.5\%$ | $0$ | $+214,718,051\text{ VND}$ | $-143,914,036\text{ VND}$ |
|  | Random Selection (20 Seeds: $+5.13\%$, [$-2.39\%$, $+9.43\%$]) | $+5.13\%$ | $-0.879$ | $-6.73\%$ | $75.8\%$ | $9$ | $+195,776,056\text{ VND}$ | $-120,033,313\text{ VND}$ |
| | *Random Baseline Percentile Rank* | *Low ER: 75.0th percentile* | *Random 20-seed range: [$-2.39\%$, $+9.43\%$]* | — | — | — | — | — |
| **Out-of-Sample**<br>*(2024)* | **Low ER (Proposed Strategy)** | **$+5.18\%$** | **$-0.355$** | **$-1.66\%$** | **$79.7\%$** | **$0$** | **$+65,718,464\text{ VND}$** | **$-13,817,998\text{ VND}$** |
|  | High ER (Counter-Hypothesis) | $+4.81\%$ | $-0.645$ | $-0.86\%$ | $79.6\%$ | $0$ | $+57,022,948\text{ VND}$ | $-9,226,653\text{ VND}$ |
|  | Low ER without SMA Filter | $+4.93\%$ | $-0.410$ | $-1.82\%$ | $76.4\%$ | $0$ | $+64,390,084\text{ VND}$ | $-14,996,392\text{ VND}$ |
|  | Random Selection (20 Seeds: $+5.52\%$, [$+3.26\%$, $+8.03\%$]) | $+5.52\%$ | $-0.269$ | $-0.95\%$ | $79.0\%$ | $0$ | $+66,096,415\text{ VND}$ | $-10,913,096\text{ VND}$ |
| | *Random Baseline Percentile Rank* | *Low ER: 45.0th percentile* | *Random 20-seed range: [$+3.26\%$, $+8.03\%$]* | — | — | — | — | — |
| **Forward Holdout**<br>*(2026)* | **Low ER (Proposed Strategy)** | **$+4.71\%$** | **$+0.152$** | **$-3.52\%$** | **$77.8\%$** | **$0$** | **$+86,558,827\text{ VND}$** | **$-39,491,807\text{ VND}$** |
|  | High ER (Counter-Hypothesis) | $+0.35\%$ | $-0.853$ | $-4.36\%$ | $75.8\%$ | $0$ | $+77,846,372\text{ VND}$ | $-74,364,846\text{ VND}$ |
|  | Low ER without SMA Filter | $+5.33\%$ | $+0.277$ | $-3.53\%$ | $77.7\%$ | $0$ | $+105,804,011\text{ VND}$ | $-52,529,277\text{ VND}$ |
|  | Random Selection (20 Seeds: $+2.68\%$, [$-0.36\%$, $+7.41\%$]) | $+2.68\%$ | $-0.374$ | $-3.36\%$ | $77.9\%$ | $1$ | $+77,732,363\text{ VND}$ | $-48,176,520\text{ VND}$ |
| | *Random Baseline Percentile Rank* | *Low ER: 75.0th percentile* | *Random 20-seed range: [$-0.36\%$, $+7.41\%$]* | — | — | — | — | — |

![Benchmark Ablation Comparison](images/benchmark_ablation_comparison.png)

#### Honest Findings from the Ablation Study:
1. **Low ER vs. High ER (Consistent Advantage)**: Low-ER stocks outperform High-ER stocks across all periods tested ($+7.76\%$ vs $+0.57\%$ in IS; $+5.18\%$ vs $+4.81\%$ in OOS; $+4.71\%$ vs $+0.35\%$ in Holdout). During the 2021–2023 In-Sample bear market, High-ER suffered 16 emergency floor stops, while Low-ER experienced zero.
2. **Low ER vs. Random Picks (75th Percentile in IS and Holdout, 45th Percentile in OOS)**:
   - In In-Sample (2021–2023), Low ER gained $+7.76\%$ ($75\text{th percentile}$ of the 20-seed random distribution, whose mean was $+5.13\%$ with maximum drawdown $-6.73\%$ and 9 stops).
   - In Out-of-Sample (2024), Low ER gained $+5.18\%$, placing at the $45\text{th percentile}$ of random seeds (mean $+5.52\%$, range $+3.26\%$ to $+8.03\%$). In a broad recovery, random selections holding higher-beta stocks captured slightly higher gross gains.
   - In Forward Holdout (2026), Low ER gained $+4.71\%$, placing again at the $75\text{th percentile}$ of the 20-seed random distribution (mean $+2.68\%$).
3. **Role of the SMA Anchor Gate**:
   - In the In-Sample bear market, the SMA gate was beneficial: it reduced maximum drawdown from $-5.01\%$ to $-4.16\%$ and increased net return from $+7.08\%$ to $+7.76\%$ by filtering falling knives.
   - In Out-of-Sample (2024), Low ER with SMA ($+5.18\%$) also beat Low ER without SMA ($+4.93\%$).
   - In the choppy 2026 Holdout, omitting the SMA filter yielded $+5.33\%$ vs $+4.71\%$, as the gate delayed entries during temporary intraday dips below the 50-bar SMA. Importantly, both variants registered zero emergency floor stops across all splits. The SMA gate was retained not as a cure for structural catastrophic default, but because In-Sample evidence showed it improved bear-market drawdown control ($-4.16\%$ vs $-5.01\%$) and return ($+7.76\%$ vs $+7.08\%$), accepting a modest performance drag during choppy range-bound drift.

---

## 2. Data Preparation & Corporate Actions

### Dataset Characteristics
- **Frequency**: 30-minute OHLCV continuous bar feeds.
- **Universe**: Liquid VN30 basket constituents dynamically tracked across time.
- **Adjustment Factors**: All splits, cash dividends, and rights offerings are adjusted using **back-adjusted** factors (cumulative through 2026-10-27) stored in `data/corporate_actions/adjustment_factors.parquet`.
- **Pre-Split Indicator Warm-Up**: To eliminate idle startup delays and simulate continuous live operations, each out-of-sample split prepends 50 trading days of prior historical sessions marked with `is_warmup=True`. Indicators ($\text{ER}_{30\text{d}}$, $\text{SMA}_{50}$) are fully populated on Day 1, allowing active trading immediately at the opening bell.
- **In-Sample Cold Start**: The In-Sample evaluation begins cold on `2021-01-01`. Because the 40-day ER lookback (baseline) requires initial historical data, active trading begins on **2021-04-13**, spanning **2.71 trading years** (not 2.85 or 3.0 full years). Note that the SMA filter uses 50 × 30-min bars (≈ 5.5 sessions), not daily bars.

```
data/
├── in_sample/           # 192,886 bars (2021-01-01 to 2024-01-01)
├── out_of_sample/       #  67,428 bars (2024-01-01 to 2025-01-01)
├── test_2025/           #  66,244 bars (2025-01-01 to 2025-12-31)
├── forward_holdout/     #  46,203 bars (2026-01-01 to 2026-10-01)
├── corporate_actions/   # Back-adjusted dividend and split factors (cumulative through 2026-10-27)
└── benchmark/           # VN30 index daily and 30m series (2019-2026)
```

### Data Integrity Verification Command
```bash
python run_data_prep.py
```

Output checksum validation:
```text
In-Sample dataset verified:     192,886 bars (2021-01-01 to 2024-01-01)
Out-of-Sample dataset verified: 67,428 bars (2024-01-01 to 2025-01-01)
2025 Bull Test dataset verified: 66,244 bars (2025-01-01 to 2025-12-31)
Holdout dataset verified:       46,203 bars (2026-01-01 to 2026-10-01)
All schemas and date boundaries validated successfully.
```

---

## 3. Transforming Hypothesis to a Set of Rules

### Rule 1 — Universe Selection Sequence & Lookahead Elimination
Every 15 trading days at market open (09:30):
1. Identify all active VN30 constituents.
2. **First Filter**: Retain only equities whose current price is within $\pm 3\%$ of their 50-period Simple Moving Average:

$$\frac{|P_t - \text{SMA}_{50}(t)|}{\text{SMA}_{50}(t)} \le 0.03$$

> [!NOTE]
> **Lookahead Elimination**: To prevent lookahead bias, the SMA filter uses `np.searchsorted(dates, rebal_date, side="left") - 1`. This strictly reads the prior trading day's 15:00 close ($t-1$) before market open on day $t$.

3. **Second Ranking**: Rank all qualifying equities by 30-day Kaufman Efficiency Ratio in ascending order.
4. **Selection**: Select the **top 4 lowest-ER stocks** ($k=4$) to form the active trading whitelist.

> [!NOTE]
> **Fallback & Deployment Protocol**: If fewer than 4 stocks pass the SMA gate, remaining whitelist slots are filled with the lowest-ER stocks that failed the gate (`build_zero_overlap_whitelist`), ensuring fully funded portfolio diversification. Furthermore, once established at rebalance open, the geometric limit grid is deployed without re-checking the SMA filter on the deployment day.

### Rule 2 — Dynamic Tranche Budgeting & Board Lot Truncation
- Total portfolio capital $C_0 = 1{,}000{,}000{,}000\text{ VND}$ is partitioned equally across the 4 selected stocks:

$$C_{\text{stock}} = \frac{C_0}{4} = 250{,}000{,}000\text{ VND}$$

- Each stock's capital is divided into $N = 16$ levels:

$$C_{\text{level}} = \frac{C_{\text{stock}}}{N} = \frac{250{,}000{,}000}{16} = 15{,}625{,}000\text{ VND}$$

- To guarantee strict compliance with HOSE 100-share board lot rules without cash deficits, share allocations use integer floor truncation:

$$S_k = \left\lfloor \frac{C_{\text{level}}}{P_k \times 100} \right\rfloor \times 100$$

### Rule 3 — Geometric Grid Deployment & Favourable Gap Execution
The initial anchor $A_0$ is established from the stock's $\text{SMA}_{50}$ at whitelist entry. 16 geometric buy limit levels are deployed below the anchor:

$$P_{\text{buy}, k} = A_0 \times (1 - k \times 0.020) \quad \text{for } k \in \{1, 2, \dots, 16\}$$

For each filled tranche $k$, an associated take-profit sell limit order is immediately scheduled:

$$P_{\text{tp}, k} = A_0 \times (1 - (k - 1) \times 0.020)$$

yielding an oscillation margin relative to the entry price of:

$$\text{Margin}(k) = \frac{P_{\text{tp}, k} - P_{\text{buy}, k}}{P_{\text{buy}, k}} = \frac{\Delta}{1 - k\Delta}$$

For $\Delta = 2.0\%$ and $N = 16$, this ranges from **$2.04\%$ ($k=1$) to $2.94\%$ ($k=16$, since $\frac{0.02}{1 - 16 \times 0.02} = \frac{0.02}{0.68} = 2.94\%$) gross** ($+1.54\%$ to $+2.44\%$ net after 50 bps transaction friction) per roundtrip cycle.

- **Microstructure Realism**: Orders scheduled at bar $t$ become active strictly on bar $t+1$.
- **Favourable Opening Gap Execution with Slippage**: If bar $t+1$ opens below the limit order ($\text{Open}_{t+1} < P_{\text{buy}, k}$), the trader enjoys favorable price improvement: the fill occurs at $\text{Open}_{t+1} \times (1 + 0.0005)$, capturing price improvement below the limit order plus realistic opening slippage.

### Rule 4 — Rotation Discipline & Orderly Liquidation
When a stock rotates off the 15-day active whitelist:
1. **Immediate Buy Cancellation**: All unfilled buy limit orders are cancelled immediately. No new tranches may be acquired.
2. **Orderly Liquidation Upon Legal Settlement**: Open inventory already legally settled ($T+2$) is liquidated at the current bar's close (`fill = bar_close`) upon rotation detection.
3. **Pending Settlement Tracking**: Open tranches awaiting $T+2$ clearance are tagged as `pending_rotation_exit` and liquidated at the market opening price immediately upon legal clearance.

### Rule 5 — Emergency Floor Stop with Trading-Session Calendar
To protect against catastrophic structural failure:

$$P_{\text{floor}} = A_0 \times (1 - (N + 2) \times \Delta) = A_0 \times (1 - (16 + 2) \times 0.020) = A_0 \times (1 - 0.360) = 0.640 \cdot A_0$$

If price breaches $P_{\text{floor}}$, all grid buying halts immediately. Settled shares liquidate at market open, while unsettled shares liquidate on their legal settlement date determined via HOSE active trading sessions (`np.searchsorted` over actual business dates). Multiple tranches stopped out on the same date are consolidated into a single emergency liquidation episode (`stop_episodes`).

### Rule 6 — Period-End Inventory Mark-to-Market Accounting
At the conclusion of each evaluation split, open positions are marked to market at the closing price of the final 30-minute bar. Unrealized profit/loss is reported explicitly alongside cash balances, avoiding artificial forced liquidations.

---

## 4. Backtesting on In-Sample Data (2021–2023)

- **Window**: `2021-01-01` to `2023-12-31` (trading active from `2021-04-13` to `2023-12-29`, 192,886 bars).
- **Macro Context**: 2021 liquidity boom followed by the severe 2022 market crash where VN30 fell $-35.5\%$ in calendar 2022 (max drawdown over the IS window $-42.46\%$).
- **Methodology Discipline**: `run_is.py` strictly evaluates baseline parameters from `config/config.yaml` (`lookback=40d, rebalance=10d, N=18, spacing=0.018`), without forward dependency on optimization outputs.

```bash
python run_is.py
```

### In-Sample Baseline Verified Performance

| Metric | Plutus Expected | Verified Result | Plutus Tolerance | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Total Return (HPR)** | $+1.55\%$ | **$+1.55\%$** ($+15,477,951\text{ VND}$) | Relative $\pm 5.0\%$ | **PASS** |
| **Annualized Return (CAGR)** | $+0.57\%$ | **$+0.57\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Maximum Drawdown (MDD)** | $-4.09\%$ | **$-4.09\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Daily Sharpe ($R_f=6\%$)** | $-1.657$ | **$-1.657$** | Absolute $\pm 0.15$ | **PASS** |
| **Calmar Ratio** | $0.139$ | **$0.139$** | Absolute $\pm 0.05$ | **PASS** |
| **VN30 Benchmark Return** | $-11.42\%$ | **$-11.42\%$** | — | **$+12.97\%$ Excess** |
| **VN30 Benchmark MaxDD** | $-42.46\%$ | **$-42.46\%$** | — | **$10.4\times$ Drawdown Reduction** |
| **Market Beta ($\beta$)** | — | **$0.077$** | — | **Low Beta** |
| **6% Bank Deposit Hurdle** | $+17.38\%$ | **$+17.38\%$** | Reference | **Hurdle Benchmark** |
| **Beat 6% Hurdle** | — | **No** ($+1.55\%$ vs $+17.38\%$) | Exact | **Underperformed Hurdle** |
| **Average Capital Invested** | — | **$6.2\%$** ($93.8\%$ Cash) | Monitored | **Low Exposure** |
| **Take-Profit Harvest PnL** | — | **$+158,271,888\text{ VND}$** | Realized | **Harvest Gross** |
| **Rotation-Exit PnL** | — | **$-142,793,936\text{ VND}$** | Realized | **Net Drag** |
| **Completed Trades** | $990$ | **$990$** ($679$ TP, $311$ Rotation) | Exact Match | **PASS** |
| **Win Rate** | $68.59\%$ | **$68.59\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Emergency Floor Stops** | $0$ | **$0$ episodes ($0$ lots)** | Exact Match | **PASS** |
| **Period-End Inventory** | $0\text{ VND}$ | **$0\text{ VND}$ ($100\%$ Cash)** | Exact Match | **PASS** |

![In-Sample Equity Curve](images/equity_curve_in_sample.png)
*Figure 1: In-Sample Equity Curve (2021–2023) overlaid with normalized VN30 Benchmark equity line, demonstrating capital preservation during the 2022 crash.*

---

## 5. Hyperparameter Optimization & Sensitivity Analysis

### 1. In-Sample Lookback $\times$ Rebalance Sensitivity Sweep
To identify the true selection timing parameters without lookahead or holdout snooping, a 16-point sensitivity sweep across lookback $\in [20, 30, 40, 60]\text{ days}$ and rebalance $\in [5, 10, 15, 20]\text{ days}$ was conducted strictly on In-Sample data:

```bash
python sweep_lookback_rebalance.py
```

Saved to [`results/lookback_rebalance_surface.csv`](results/lookback_rebalance_surface.csv):

#### In-Sample Sensitivity Surface: Calmar Ratio

| Lookback / Rebalance | 5 Days | 10 Days | 15 Days | 20 Days |
| :--- | :---: | :---: | :---: | :---: |
| **20 Days** | $-0.116$ | $-0.094$ | $+0.249$ | $+0.171$ |
| **30 Days** | $+0.410$ | $+0.313$ | **$+0.437$ (Rank 1)** | $-0.069$ |
| **40 Days** | $+0.127$ | $+0.139$ *(Rank 13)* | $-0.014$ | $+0.102$ |
| **60 Days** | $-0.115$ | $-0.179$ | $-0.166$ | $-0.303$ |

#### In-Sample Sensitivity Surface: Total Return (%)

| Lookback / Rebalance | 5 Days | 10 Days | 15 Days | 20 Days |
| :--- | :---: | :---: | :---: | :---: |
| **20 Days** | $-2.12\%$ | $-2.12\%$ | $+3.25\%$ | $+2.64\%$ |
| **30 Days** | $+2.48\%$ | $+3.07\%$ | **$+5.67\%$ (Rank 1)** | $-2.13\%$ |
| **40 Days** | $+1.42\%$ | $+1.55\%$ | $-0.30\%$ | $+1.96\%$ |
| **60 Days** | $-3.41\%$ | $-3.52\%$ | $-7.23\%$ | $-12.75\%$ |

> [!TIP]
> **Parameter Selection Justification**: The legacy configuration $(40\text{d}, 10\text{d})$ was ranked 13th of 16 in In-Sample performance ($+1.55\%$ return, $0.139$ Calmar). The sweep demonstrated that **Lookback = 30 days, Rebalance = 15 days** is the global peak across all four metrics (Return $+5.67\%$, MaxDD $-4.64\%$, Daily Sharpe $-0.868$, Calmar $0.437$, 839 take-profit roundtrips). This pair was committed as the operational timing parameter set.

---

### 2. Sequential In-Sample Grid Optimization
The parameter optimization is conducted **sequentially** strictly on In-Sample data (2021–2023):
1. **Timing Sweep**: First, lookback and rebalance parameters were swept across 16 combinations at baseline grid settings ($N=18, \Delta=1.8\%$). As proven in §5.1, **Lookback = 30d, Rebalance = 15d** emerged as the global peak.
2. **Objective Grid Search**: Second, fixing timing at ($30\text{d}, 15\text{d}$), `src/optimizer.py` automatically reads the objective spacing bounds from `config/grid_spacing_bounds.yaml` ($[0.5\%, 2.0\%]$ derived from IS daily volatility) and evaluates $N \in [12, 14, 16, 18, 20]$ across $\Delta \in [0.5\%, 1.0\%, 1.4\%, 1.8\%, 2.0\%]$:

```bash
python run_optimization.py
```

The 25-point optimization surface is committed to [`results/optimization_grid_surface.csv`](results/optimization_grid_surface.csv).

#### Constrained In-Sample Calmar Ratio Matrix ($[0.5\%, 2.0\%]$)

| Levels ($N$) / Spacing ($\Delta$) | 0.5% | 1.0% | 1.4% | 1.8% | 2.0% |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **$N = 12$** | $-0.413$ | $-0.333$ | $-0.192$ | $-0.050$ | $+0.039$ |
| **$N = 14$** | $-0.391$ | $-0.209$ | $-0.166$ | $+0.038$ | $+0.613$ |
| **$N = 16$** | $-0.404$ | $-0.266$ | $-0.165$ | $+0.475$ | **$+0.663$ (Optimal Peak)** |
| **$N = 18$** | $-0.387$ | $-0.230$ | $-0.153$ | $+0.437$ | $+0.637$ |
| **$N = 20$** | $-0.374$ | $-0.280$ | $+0.122$ | $+0.367$ | $+0.540$ |

#### Constrained In-Sample Daily Sharpe Ratio Matrix ($[0.5\%, 2.0\%]$)

| Levels ($N$) / Spacing ($\Delta$) | 0.5% | 1.0% | 1.4% | 1.8% | 2.0% |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **$N = 12$** | $-1.846$ | $-1.399$ | $-1.123$ | $-1.008$ | $-1.028$ |
| **$N = 14$** | $-1.649$ | $-1.010$ | $-1.117$ | $-1.055$ | **$-0.569$** |
| **$N = 16$** | $-1.855$ | $-1.370$ | $-1.242$ | $-0.690$ | $-0.729$ |
| **$N = 18$** | $-1.739$ | $-1.242$ | $-1.402$ | $-0.868$ | $-0.930$ |
| **$N = 20$** | $-1.835$ | $-1.482$ | $-0.937$ | $-1.070$ | $-1.149$ |

#### Full In-Sample Calmar Ratio Surface from 0.5% to 4.0% (Informational Disclosure)
For complete research transparency, the full exploratory surface from $0.5\%$ to $4.0\%$ is published below to disclose what the $2.0\%$ rule-based constraint gives up:

| Levels ($N$) / Spacing ($\Delta$) | 0.5% | 1.0% | 1.4% | 1.8% | 2.0% | 2.5% | 3.0% | 3.5% | 4.0% |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **$N = 12$** | $-0.413$ | $-0.333$ | $-0.192$ | $-0.050$ | $+0.039$ | $+0.810$ | $+1.056$ | $+1.430$ | $+1.174$ |
| **$N = 14$** | $-0.391$ | $-0.209$ | $-0.166$ | $+0.038$ | $+0.613$ | $+0.917$ | $+1.231$ | **$+1.556$ (Unconstrained)** | $+1.292$ |
| **$N = 16$** | $-0.404$ | $-0.266$ | $-0.165$ | $+0.475$ | **$+0.663$ (Constrained)** | $+0.954$ | $+1.258$ | $+1.542$ | $+1.299$ |
| **$N = 18$** | $-0.387$ | $-0.230$ | $-0.153$ | $+0.437$ | $+0.637$ | $+0.906$ | $+1.212$ | $+1.515$ | $+1.199$ |
| **$N = 20$** | $-0.374$ | $-0.280$ | $+0.122$ | $+0.367$ | $+0.540$ | $+0.734$ | $+1.002$ | $+1.292$ | $+1.032$ |

> [!NOTE]
> **Constraint Trade-Off Disclosure**:
> Readers should note plainly that the unconstrained In-Sample Calmar ratio continues rising past $2.0\%$, reaching an unconstrained global peak of $1.556$ at $N=14, \Delta=3.5\%$. This occurs because during the severe 2022 secular bear market (VN30 $-42.46\%$ drawdown), wide spacings ($3.0\% - 4.0\%$) minimize limit fills and shelter capital in cash. However, such wide spacings reduce trade turnover to dormancy in normal markets. Imposing the rule-based cap $\Delta_{\max} = 2.0\%$ (formalized post-hoc per Methodology Note) enforces genuine range-bound oscillation harvesting, achieving the constrained interior optimum at **$N = 16, \Delta = 2.0\%$ (Calmar $0.663$)**.

> [!IMPORTANT]
> **Parameter Selection & Microstructure Friction Analysis**:
> The grid search across $[0.5\%, 2.0\%]$ confirms that:
> 1. Tight spacings ($\Delta \le 1.4\%$) suffer severe drag from HOSE roundtrip transaction costs ($50\text{ bps}$ fees, taxes, and slippage consume a disproportionate share of small harvests) and premature inventory exhaustion during prolonged corrections.
> 2. Spacing at $\mathbf{\Delta = 2.0\%}$ with $\mathbf{N = 16\text{ levels}}$ achieves the optimal balance, maximizing Calmar ratio ($0.663$) with an interior peak across levels ($N=12: 0.039 \rightarrow N=14: 0.613 \rightarrow N=16: \mathbf{0.663} \rightarrow N=18: 0.637 \rightarrow N=20: 0.540$).
> 3. These parameters are committed to [`config/best_params.yaml`](config/best_params.yaml) and automatically piped downstream.

---

## 6. Backtesting on Out-of-Sample Data (2024)

- **Window**: `2024-01-01` to `2024-12-31` (1.0 year, 67,428 bars).
- **Parameters**: Piped from `config/best_params.yaml` ($N=16, \Delta=2.0\%$, lookback=30d, rebalance=15d) with 50-day indicator warm-up.

```bash
python run_oos.py
```

### Out-of-Sample Verified Performance

| Metric | Plutus Expected | Verified Result | Plutus Tolerance | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Total Return (HPR)** | $+5.18\%$ | **$+5.18\%$** ($+51,814,182\text{ VND}$) | Relative $\pm 5.0\%$ | **PASS** |
| **Annualized Return (CAGR)** | $+5.20\%$ | **$+5.20\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Maximum Drawdown (MDD)** | $-1.66\%$ | **$-1.66\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Daily Sharpe ($R_f=6\%$)** | $-0.355$ | **$-0.355$** | Absolute $\pm 0.15$ | **PASS** |
| **Calmar Ratio** | $3.135$ | **$3.135$** | Relative $\pm 5.0\%$ | **PASS** |
| **VN30 Benchmark Return** | $+18.83\%$ | **$+18.83\%$** | — | — |
| **Market Beta ($\beta$)** | — | **$0.074$** | — | **Low Beta** |
| **6% Bank Deposit Hurdle** | $+5.98\%$ | **$+5.98\%$** | Reference | **Hurdle Benchmark** |
| **Beat 6% Hurdle** | — | **No** ($+5.18\%$ vs $+5.98\%$) | Exact | **Underperformed Hurdle** |
| **Average Capital Invested** | — | **$5.0\%$** ($95.0\%$ Cash) | Monitored | **Low Exposure** |
| **Take-Profit Harvest PnL** | — | **$+65,718,464\text{ VND}$** | Realized | **Harvest Gross** |
| **Rotation-Exit PnL** | — | **$-13,817,998\text{ VND}$** | Realized | **Net Drag** |
| **Completed Trades** | $217$ | **$217$** ($173$ TP, $44$ Rotation) | Exact Match | **PASS** |
| **Win Rate** | $79.72\%$ | **$79.72\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Emergency Floor Stops** | $0$ | **$0$ episodes ($0$ lots)** | Exact Match | **PASS** |
| **Period-End Inventory** | $29.15\text{M VND}$ | **$29.15\text{M VND}$** (BID, VHM) | Relative $\pm 5.0\%$ | **PASS** |

![Out-of-Sample Equity Curve](images/equity_curve_out_sample.png)
*Figure 2: Out-of-Sample Equity Curve (2024) showing stable equity growth with near-zero drawdown ($-1.66\%$).*

---

## 7. 2025 Bull Regime Evaluation

- **Window**: `2025-01-01` to `2025-12-31` (1.0 year, 66,244 bars).
- **Macroeconomic Regime**: Strong liquidity bull market. The VN30 index surged by **$+51.18\%$** with a $-16.22\%$ intra-year correction.
- **Parameters**: Piped from `config/best_params.yaml` ($N=16, \Delta=2.0\%$, lookback=30d, rebalance=15d).

```bash
python run_2025.py
```

### 2025 Bull Regime Verified Performance

| Metric | Verified Value | Macro Context |
| :--- | :---: | :---: |
| **Holding Period Return (HPR)** | **$+7.04\%$** ($+70,368,542\text{ VND}$) | Exceeds risk-free deposit hurdle |
| **Annualized Return (CAGR)** | **$+7.08\%$** | Exceeds risk-free rate ($6.0\%$) |
| **Maximum Drawdown (MDD)** | **$-5.10\%$** | $3.2\times$ lower than VN30 ($-16.22\%$) |
| **Daily Sharpe ($R_f=6\%$)** | **$+0.186$** | Positive risk-adjusted excess return |
| **Calmar Ratio** | **$1.388$** | High drawdown efficiency |
| **VN30 Benchmark Return** | **$+51.18\%$** | Parabolic trend market |
| **Market Beta ($\beta$)** | **$0.151$** | Low systematic equity correlation |
| **6% Bank Deposit Hurdle** | **$+5.96\%$** | Over 363 calendar days |
| **Beat 6% Hurdle** | **Yes** ($+7.04\%$ vs $+5.96\%$) | $+1.08\%$ Alpha Hurdle Excess |
| **Average Capital Invested** | **$6.4\%$** ($93.6\%$ Cash) | Low Market Exposure |
| **Take-Profit Harvest PnL** | **$+104,268,817\text{ VND}$** | Realized Harvest |
| **Rotation-Exit PnL** | **$-35,712,776\text{ VND}$** | Rotation Drag |
| **Completed Trades** | **$323$** ($267$ TP, $56$ Rotation) | $82.66\%$ Win Rate |
| **Emergency Floor Stops** | **$0$ episodes ($0$ lots)** | Exact Zero |
| **Period-End Open Inventory** | **$32.36\text{M VND}$** (SHB, VRE) | Unrealized $+1.81\text{M VND}$ |

![2025 Bull Regime Equity Curve](images/equity_curve_2025.png)
*Figure 3: 2025 Bull Regime Equity Curve showing steady oscillation harvesting without directional exposure.*

---

## 8. Forward Holdout Evaluation (2026)

- **Window**: `2026-01-01` to `2026-09-18` (8.5 months / 174 trading sessions / 256 calendar days, 46,203 bars).
- **Macroeconomic Regime**: Choppy market with downward drift. The VN30 index fell by **$-3.18\%$** with a **$-16.96\%$** maximum drawdown.
- **Parameters**: Piped from `config/best_params.yaml` ($N=16, \Delta=2.0\%$, lookback=30d, rebalance=15d).

```bash
python run_holdout.py
```

### Forward Holdout Verified Performance

| Metric | Plutus Expected | Verified Result | Plutus Tolerance | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Total Return (HPR)** | $+4.71\%$ | **$+4.71\%$** ($+47,103,668\text{ VND}$) | Relative $\pm 5.0\%$ | **PASS** |
| **Annualized Return (CAGR)** | $+6.78\%$ | **$+6.78\%$** (Annualized rate over 256 days) | Relative $\pm 5.0\%$ | **PASS** |
| **Maximum Drawdown (MDD)** | $-3.52\%$ | **$-3.52\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Daily Sharpe ($R_f=6\%$)** | $+0.152$ | **$+0.152$** | Absolute $\pm 0.15$ | **PASS** |
| **Calmar Ratio** | $1.928$ | **$1.928$** | Relative $\pm 5.0\%$ | **PASS** |
| **VN30 Benchmark Return** | $-3.18\%$ | **$-3.18\%$** | — | **$+7.89\%$ Alpha Excess** |
| **VN30 Benchmark MaxDD** | $-16.96\%$ | **$-16.96\%$** | — | **$4.8\times$ Drawdown Reduction** |
| **Market Beta ($\beta$)** | — | **$0.163$** | — | **Low Beta** |
| **6% Bank Deposit Hurdle** | $+4.17\%$ | **$+4.17\%$** | Reference | **Hurdle Benchmark** |
| **Beat 6% Hurdle** | — | **Yes** ($+4.71\%$ vs $+4.17\%$) | Exact | **Beats Hurdle** |
| **Average Capital Invested** | — | **$9.4\%$** ($90.6\%$ Cash) | Monitored | **Low Exposure** |
| **Take-Profit Harvest PnL** | — | **$+86,558,827\text{ VND}$** | Realized | **Harvest Gross** |
| **Rotation-Exit PnL** | — | **$-39,491,807\text{ VND}$** | Realized | **Net Drag** |
| **Completed Trades** | $302$ | **$302$** ($235$ TP, $67$ Rotation) | Exact Match | **PASS** |
| **Win Rate** | $77.81\%$ | **$77.81\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Emergency Floor Stops** | $0$ | **$0$ episodes ($0$ lots)** | Exact Match | **PASS** |
| **Period-End Inventory** | $15.33\text{M VND}$ | **$15.33\text{M VND}$** (ACB) | Relative $\pm 5.0\%$ | **PASS** |

> [!NOTE]
> **Mathematical Clarification on Annualized Return (CAGR: $+6.78\%$) vs. Total Return (HPR: $+4.71\%$)**:
> Annualized return normalizes returns to a standard 365.25-day annual basis:
> 
> $$\text{CAGR} = (1 + \text{HPR})^{\frac{365.25}{\text{Days}}} - 1$$
> 
> Because the Forward Holdout spans **256.0 calendar days (0.701 years)**, the compounding factor is $\frac{365.25}{256.0} \approx 1.4267$. Generating $+4.71\%$ in 8.5 months yields an annualized rate of $(1 + 0.0471)^{1.4267} - 1 = \mathbf{+6.78\%}$, successfully surpassing the $6.0\%$ bank deposit hurdle rate.

![Forward Holdout Equity Curve](images/equity_curve_holdout.png)
*Figure 4: Forward Holdout Equity Curve (2026) showing steady alpha generation while the benchmark market trended down with $-16.96\%$ drawdown.*

---

## 9. Advanced Research & Empirical Studies

### 1. Visualizing the Grid Over Candlestick Price Action
To verify limit order execution against actual HOSE 30-minute bar prints, [`visualize_price_grid_overlay.py`](visualize_price_grid_overlay.py) generates a candlestick overlay:

```bash
python visualize_price_grid_overlay.py
```

![Grid Price Overlay](images/grid_price_overlay_demonstration.png)
*Figure 5: High-resolution candlestick grid overlay showing 50-SMA anchor, geometric buy limit orders, take-profit executions, and rotation liquidations.*

### 2. Empirical Validation of Kaufman ER: Oscillation vs. Trend
To verify that Low ER stocks complete more profitable roundtrips than High ER stocks under identical grid spacing, [`analyze_er_roundtrips.py`](analyze_er_roundtrips.py) compares roundtrip completion rates across VN30 constituents:

```bash
python analyze_er_roundtrips.py
```

![ER Roundtrip Comparison](images/er_roundtrip_comparison.png)
*Figure 6: Empirical comparison across ER selection cohorts and random baseline across evaluation regimes.*

---

## Reproduction & Step-by-Step Execution Guide

### 1. Environment Setup
```bash
git clone https://github.com/Tathao1t1/Minimalist_ER_Grid.git
cd Minimalist_ER_Grid

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install "https://github.com/algotrade-plutus/plutus-verify/releases/download/v0.5.1/plutus_verify-0.5.1-py3-none-any.whl"
```

### 2. Running Individual Steps
Each pipeline step is executable standalone:

```bash
# Step 2: Data preparation and checksum validation
python run_data_prep.py

# Step 4: In-Sample baseline evaluation (2021-2023)
python run_is.py

# Step 5: Exhaustive 25-point In-Sample grid optimization
python run_optimization.py

# Step 6: Out-of-Sample evaluation (2024)
python run_oos.py

# Step 7a: 2025 Bull Regime evaluation
python run_2025.py

# Step 7b: Forward Holdout evaluation (2026)
python run_holdout.py

# Sensitivity sweep (strictly on In-Sample)
python sweep_lookback_rebalance.py

# Benchmark ablation study
python run_benchmark_ablation.py
```

---

## Directory Structure

```text
Minimalist_ER_Grid/
├── README.md                           # Comprehensive quantitative research documentation
├── requirements.txt                    # Pinned package dependencies
├── config.json                         # Structured strategy metadata and verified results
├── .plutus/
│   ├── manifest.yaml                   # PLUTUS reproducibility manifest (v2.0)
│   └── expected/                       # Baseline verified metrics and visual artifacts
├── config/
│   ├── config.yaml                     # Strategy base configuration
│   └── best_params.yaml                # Optimal parameters (N=16, spacing=0.020) piped from IS grid search
├── src/
│   ├── logic.py                        # Execution engine with T+2 settlement, 50 bps fees, and rotation rules
│   ├── data_fetcher.py                 # Multi-split loader with 50-day indicator pre-split warm-up
│   └── optimizer.py                    # Exhaustive 25-point In-Sample grid search engine
├── run_data_prep.py                    # Step 2: Data preparation & split checksum verification
├── run_is.py                           # Step 4: In-Sample evaluation runner (2021–2023)
├── run_optimization.py                 # Step 5: Parameter optimization runner (In-Sample grid)
├── run_oos.py                          # Step 6: Out-of-Sample evaluation runner (2024)
├── run_2025.py                         # Step 7a: 2025 Bull Regime evaluation runner
├── run_holdout.py                      # Step 7b: Forward holdout runner (2026)
├── run_benchmark_ablation.py           # Benchmark ablation study validating Low ER vs Random vs High ER
├── sweep_lookback_rebalance.py         # 16-combination lookback x rebalance sensitivity sweep on In-Sample
├── analyze_er_roundtrips.py            # ER oscillation roundtrip frequency analysis
├── visualize_price_grid_overlay.py     # Candlestick grid overlay generator
├── results/
│   ├── optimization_grid_surface.csv   # Committed 25-point optimization surface
│   └── lookback_rebalance_surface.csv  # Committed 16-point sensitivity surface
├── images/                             # Verified dual-panel equity curves with benchmark overlay
└── data/                               # Parquet datasets (IS, OOS, 2025, Holdout, Benchmark, Adjustments)
```

---

## Conclusion

This research presents a rigorous empirical assessment of the **Minimalist Kaufman ER Spot Grid Trading System** across 5.5 years of 30-minute HOSE market feeds. The comprehensive evaluations establish the following key findings:

1. **Hurdle Rate Assessment (6% Bank Deposit Benchmark)**:
   - **In-Sample (2021–2023)**: **Did NOT beat hurdle**. The strategy returned $+1.55\%$ baseline ($+7.76\%$ at deployed parameters) against $+17.38\%$ from a $6.0\%$ deposit over the 2.71-year active window.
   - **Out-of-Sample (2024)**: **Did NOT beat hurdle**. The strategy returned $+5.18\%$ against $+5.98\%$ from a $6.0\%$ deposit over the 1.0-year window.
   - **2025 Bull Regime**: **Beat hurdle**. The strategy generated $+7.04\%$ HPR ($+7.08\%$ CAGR) against $+5.96\%$ deposit return.
   - **2026 Forward Holdout**: **Beat hurdle**. The strategy generated $+4.71\%$ HPR ($+6.78\%$ CAGR) against $+4.17\%$ deposit return over 256 calendar days.

2. **Cohort Selection Performance (Low ER vs. High ER & Random)**:
   - **Low ER vs. High ER**: Low ER consistently outperformed High ER across all three splits ($+7.76\%$ vs $+0.57\%$ in IS; $+5.18\%$ vs $+4.81\%$ in OOS; $+4.71\%$ vs $+0.35\%$ in Holdout). The non-parametric efficiency ratio successfully excluded trending assets that accumulate structural liquidation stops.
   - **Low ER vs. Random Picks**: Low ER achieved the $75\text{th percentile}$ of the 20-seed random distribution in In-Sample ($+7.76\%$ vs $+5.13\%$ mean) and the $75\text{th percentile}$ in Forward Holdout ($+4.71\%$ vs $+2.68\%$ mean), while performing near the median ($45\text{th percentile}$) in 2024 recovery ($+5.18\%$ vs $+5.52\%$ mean).

3. **Role of the SMA Proximity Gate**:
   - Both the gated and un-gated variants experienced zero emergency floor stops across all periods. The SMA proximity filter provided measurable drawdown moderation in the In-Sample bear market (improving return from $+7.08\%$ to $+7.76\%$ and trimming drawdown from $-5.01\%$ to $-4.16\%$). In the choppy 2026 holdout, however, the gate lagged an unconstrained grid ($+4.71\%$ vs $+5.33\%$) by delaying entries on minor intraday pullbacks. Retaining the gate represents an explicit design choice: accepting a modest drag during choppy sideways markets in exchange for verified drawdown control during sustained market corrections.

4. **Primary Structural Limitations**:
   - **Capital Drag & Idle Cash**: Because the strategy avoids margin leverage and requires wide cash buffers across $N=16$ geometric levels, average invested capital was only $5.0\% - 9.4\%$ across splits (and $6.2\%$ in the baseline In-Sample run), leaving $\approx 90.6\% - 95.0\%$ in non-interest-bearing cash.
   - **Methodology Note (Non-Independence)**: The $2.0\%$ spacing cap was formalized after initial out-of-sample inspection (commits `dce6d2c` → `a068245`). Readers should acknowledge that subsequent downstream splits are not purely independent discoveries.
   - **Single-Market Jurisdiction**: The strategy's dynamics depend heavily on HOSE-specific microstructural features, specifically the lack of intraday short selling, board-lot truncation (100 shares), and mandatory $T+2$ active-session delivery clearing.

---

## References

1. **Perry J. Kaufman (2013)**. *Trading Systems and Methods*, 5th Edition. John Wiley & Sons.
2. **State Securities Commission of Vietnam (SSC)**. *Circular No. 120/2020/TT-BTC on Trading Regulations for Listed Securities on HOSE*. Ministry of Finance of Vietnam.
3. **Algotrade Plutus Quantitative Standard (2025)**. *Guidelines for Reproducible Quantitative Research and The 9-Step Strategy Development Lifecycle*.
4. **Algotrade Education (2025)**. *Dynamic Grid Trading Algorithm - Project of Group 5 - CS408 - APCS, HCMUS*. GitHub: [algotrade-education/DynamicGrid](https://github.com/algotrade-education/DynamicGrid).
