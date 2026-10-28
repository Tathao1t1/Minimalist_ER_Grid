# Kaufman-Range-Grid: Non-Parametric Kaufman ER Spot Grid Trading System
> Systematic equity oscillation harvesting engine with zero directional leverage, fully compliant with HOSE trading rules, active-session $T+2$ settlement, and institutional 50 bps execution friction.

[![Plutus Standard](https://img.shields.io/badge/PLUTUS-v2.0%20Verified-brightgreen)](file:///.plutus/manifest.yaml)
[![Python Version](https://img.shields.io/badge/Python-3.12-blue)](file:///requirements.txt)
[![Market](https://img.shields.io/badge/Exchange-HOSE%20%7C%20VN30-orange)](file:///data)
[![Transaction Costs](https://img.shields.io/badge/Costs-50%20bps%20Roundtrip-red)](file:///config/config.yaml)
[![Time-Series Discipline](https://img.shields.io/badge/Discipline-Strict%20IS%20Optimization-purple)](file:///src/optimizer.py)

---

## Abstract

The **Kaufman-Range-Grid** system is a systematic, quantitative trading strategy engineered specifically for the microstructure of the Ho Chi Minh Stock Exchange (HOSE). It combines Perry Kaufman's non-parametric **Efficiency Ratio (ER)** as a regime-selection filter with an **adaptive geometric grid execution engine**, harvesting recurring mean-reverting price oscillations without derivative exposure, margin calls, or directional leverage.

The strategy was developed and evaluated end-to-end on **HOSE 30-minute OHLCV bar feeds across the liquid VN30 constituent universe from 2021 to 2026**, adhering strictly to the [9-step Development Process](file:///Users/ttt/Final_Projects_v1/book.md) and the [Plutus Reproducibility Standard](https://github.com/algotrade-plutus/plutus-guideline). All hyperparameters were selected strictly on the In-Sample period (2021–2023) using an exhaustive 25-point grid search and committed to [`config/best_params.yaml`](file:///Users/ttt/Final_Projects_v1/strategies/minimalist_er_grid/config/best_params.yaml) before out-of-sample exposure.

### Multi-Period Performance Overview (Optimal $N=16, \Delta=2.2\%$)

| Evaluation Split | Calendar Window | Strategy HPR | Annual Return (CAGR) | Strategy MaxDD | VN30 Benchmark HPR | VN30 Benchmark MaxDD | Excess Return | Market Beta ($\beta$) | Daily Sharpe ($R_f=6\%$) | Calmar Ratio | Completed Trades (Win Rate) | Period-End Open Inventory |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **In-Sample** | 2021–2023 (3.0 yrs) | **$+2.79\%$** ($+27.9\text{M}$) | $+1.02\%$ | **$-3.85\%$** | $-11.42\%$ | **$-42.46\%$** | **$+14.21\%$** | **$0.083$** | $-1.510$ | $0.265$ | 767 ($67.0\%$) | None ($100\%$ Cash) |
| **Out-of-Sample** | 2024 (1.0 yr) | **$+5.59\%$** ($+55.9\text{M}$) | $+5.60\%$ | **$-0.91\%$** | $+18.83\%$ | $-8.38\%$ | $-13.24\%$ | **$0.045$** | $-0.247$ | **$6.153$** | 200 ($74.5\%$) | POW: $3,000$ shs ($-176\text{k}$) |
| **2025 Bull Test** | 2025 (1.0 yr) | **$+8.57\%$** ($+85.7\text{M}$) | $+8.62\%$ | **$-3.38\%$** | $+51.18\%$ | $-16.22\%$ | $-42.61\%$ | **$0.125$** | **$+0.543$** | **$2.549$** | 329 ($79.6\%$) | GVR: $2,100$ shs ($-1.31\text{M}$) |
| **Forward Holdout** | 2026 (8.5 mos) | **$+5.37\%$** ($+53.7\text{M}$) | **$+7.74\%$** | **$-2.13\%$** | $-3.18\%$ | **$-16.96\%$** | **$+8.55\%$** | **$0.094$** | **$+0.431$** | **$3.639$** | 248 ($77.4\%$) | $3$ stocks: $1,200$ shs ($+554\text{k}$) |

Every metric reported above is fully reproducible via standalone scripts and validated against `.plutus/manifest.yaml`.

---

## Introduction & HOSE Microstructure

Algorithmic trading in Vietnam's equity market requires rigorous accommodation of exchange-specific structural constraints:
1. **Settlement Restrictions (Circular 120/2020/TT-BTC)**: HOSE enforces an active-session $T+2$ settlement cycle. Shares purchased on trading day $T$ can only be legally sold after 13:00 on $T+2$. Unsettled inventory cannot be liquidated intraday, rendering unhedged scalping illegal and unfeasible.
2. **Integer Board Lots**: HOSE mandates standard board lots of 100 shares. Fractional share trading is prohibited.
3. **Institutional Execution Friction (50 bps Roundtrip)**:
   - Brokerage Buy Commission: $15\text{ bps}$ ($0.15\%$)
   - Brokerage Sell Commission: $15\text{ bps}$ ($0.15\%$)
   - Statutory Sell Tax (Ministry of Finance): $10\text{ bps}$ ($0.10\%$)
   - Conservative Gap Slippage: $5\text{ bps}$ buy $+ 5\text{ bps}$ sell ($0.10\%$)
   - **Total Roundtrip Friction: $50\text{ bps}$ ($0.50\%$)** incorporated into every simulated order fill.
4. **Retail Domination & Range-Bound Chop**: With individual retail participants accounting for over $85\%$ of trading volume, HOSE equities exhibit extensive periods of stationary consolidation accompanied by false breakout whipsaws. Conventional trend-following systems suffer repeated drawdown cycles.

The **Kaufman-Range-Grid** system directly monetizes this market behavior by supplying liquidity on geometric dips and capturing incremental profits on mean-reverting rebounds, while maintaining ultra-low market beta ($\beta \approx 0.05 - 0.12$).

---

## 1. Forming Algorithm Hypothesis

### Mathematical Definition of Kaufman Efficiency Ratio (ER)
Perry Kaufman defined market efficiency as the ratio of directional price displacement to the total path traveled over a historical window of $k$ periods:

$$\text{ER}_t(k) = \frac{|\Delta P_k|}{\sum_{i=1}^k |\Delta P_i|} = \frac{|P_t - P_{t-k}|}{\sum_{i=1}^k |P_{t-i+1} - P_{t-i}|}$$

Where:
- $P_t$ is the closing price on day $t$.
- $k$ is the lookback window ($k = 40$ trading days, approximately two business months).
- The numerator represents net directional displacement.
- The denominator represents the cumulative path volatility.

```mermaid
graph TD
    A[40-Day Price Window] --> B[Calculate Directional Displacement |Pt - Pt-k|]
    A --> C[Calculate Cumulative Absolute Path Sum]
    B & C --> D[Kaufman Efficiency Ratio ER]
    D -->|ER -> 1.0 Trending| E[Exclude from Grid: Danger of Accumulating Losing Lots]
    D -->|ER -> 0.0 Stationary Oscillation| F[Qualify for Grid Whitelist: High Take-Profit Recurrence]
```

### Regime Gating Hypothesis
- **$\text{ER} \to 1.0$ (High Efficiency / Trending Regime)**: Price travels monotonically with minimal retracement. Spot grids deployed on high ER stocks accumulate losing tranches during secular declines.
- **$\text{ER} \to 0.0$ (Low Efficiency / Stationary Oscillation)**: Price oscillates continuously across a wide band while returning close to its origin. This creates the mathematically ideal substrate for grid order recycling: limit buy orders fill on dips and take-profit sell orders execute in rapid succession.
- **Anchor Proximity Gate (Rule 1)**: Even among low ER stocks, equities detaching from their medium-term fair value must be rejected. The strategy filters for equities whose price is within $\pm 3\%$ of their 50-period Simple Moving Average ($\text{SMA}_{50}$), preventing entry during late-stage breakdown detachments.

---

## 2. Data Preparation & Corporate Actions

### Dataset Characteristics
- **Frequency**: 30-minute OHLCV continuous bar feeds.
- **Universe**: Liquid VN30 basket constituents dynamically tracked across time.
- **Adjustment Factors**: All splits, cash dividends, and rights offerings are adjusted using point-in-time adjustment factors stored in `data/corporate_actions/adjustment_factors.parquet`.
- **Pre-Split Indicator Warm-Up (P-4)**: To eliminate idle startup delays and simulate continuous live operations, each out-of-sample split prepends 40 trading days of prior historical sessions marked with `is_warmup=True`. Indicators ($\text{ER}_{40\text{d}}$, $\text{SMA}_{50}$) are fully populated on Day 1, allowing active trading immediately at the opening bell.

```
data/
├── in_sample/           # 192,886 bars (2021-01-01 to 2024-01-01)
├── out_of_sample/       #  67,428 bars (2024-01-01 to 2025-01-01)
├── test_2025/           #  66,244 bars (2025-01-01 to 2025-12-31)
├── forward_holdout/     #  46,203 bars (2026-01-01 to 2026-10-01)
├── corporate_actions/   # Point-in-time dividend and split adjustment factors
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

### Rule 1 — Universe Selection Sequence & Fair-Value Gating (`A-8`)
Every 10 trading days at market open:
1. Identify all active VN30 constituents.
2. **First Filter**: Retain only equities whose current price is within $\pm 3\%$ of their 50-period Simple Moving Average:

$$\frac{|P_t - \text{SMA}_{50}(t)|}{\text{SMA}_{50}(t)} \le 0.03$$

3. **Second Ranking**: Rank all qualifying equities by 40-day Kaufman Efficiency Ratio in ascending order.
4. **Selection**: Select the **top 4 lowest-ER stocks** ($k=4$) to form the active trading whitelist.

### Rule 2 — Dynamic Tranche Budgeting & Board Lot Truncation (`A-13`)
- Total portfolio capital $C_0 = 1{,}000{,}000{,}000\text{ VND}$ is partitioned equally across the 4 selected stocks:

$$C_{\text{stock}} = \frac{C_0}{4} = 250{,}000{,}000\text{ VND}$$

- Each stock's capital is divided into $N = 16$ levels:

$$C_{\text{level}} = \frac{C_{\text{stock}}}{N} = \frac{250{,}000{,}000}{16} = 15{,}625{,}000\text{ VND}$$

- To guarantee strict compliance with HOSE 100-share board lot rules without cash deficits, share allocations use integer floor truncation:

$$S_k = \left\lfloor \frac{C_{\text{level}}}{P_k \times 100} \right\rfloor \times 100$$

### Rule 3 — Geometric Grid Deployment & Next-Bar Execution
The initial anchor $A_0$ is established from the stock's $\text{SMA}_{50}$ at whitelist entry. 16 geometric buy limit levels are deployed below the anchor:

$$P_{\text{buy}, k} = A_0 \times (1 - k \times 0.022) \quad \text{for } k \in \{1, 2, \dots, 16\}$$

For each filled tranche $k$, an associated take-profit sell limit order is immediately scheduled:

$$P_{\text{tp}, k} = A_0 \times (1 - (k - 1) \times 0.022)$$

yielding a gross oscillation margin of $+2.20\%$ ($+1.70\%$ net of 50 bps transaction costs) per roundtrip cycle.

- **Microstructure Realism**: Orders scheduled at bar $t$ become active strictly on bar $t+1$.
- **Adverse Gap Execution**: If bar $t+1$ opens below the limit order ($\text{Open}_{t+1} < P_{\text{buy}, k}$), the fill occurs at $\text{Open}_{t+1} \times (1 + 0.0005)$, modeling adverse opening slippage.

### Rule 4 — Rotation Discipline & Orderly Liquidation (`A-7`)
When a stock rotates off the 10-day active whitelist:
1. **Immediate Buy Cancellation**: All unfilled buy limit orders are cancelled immediately. No new tranches may be acquired.
2. **Orderly Liquidation Upon Legal Settlement**: Open inventory already legally settled ($T+2$) is liquidated at the next bar's close.
3. **Pending Settlement Tracking**: Open tranches awaiting $T+2$ clearance are tagged as `pending_rotation_exit` and liquidated at the market opening price immediately upon legal clearance.
- **Audit Verification**: This protocol completely eliminated unauthorized entries ($0\%$ off-whitelist buys across all evaluation windows).

### Rule 5 — Emergency Floor Stop with Trading-Session Calendar (`A-3`, `A-12`)
To protect against catastrophic structural failure:

$$P_{\text{floor}} = A_0 \times (1 - (N + 2) \times 0.022) = A_0 \times (1 - 18 \times 0.022) = 0.604 \times A_0$$

If price breaches $P_{\text{floor}}$, all grid buying halts immediately. Settled shares liquidate at market open, while unsettled shares liquidate on their legal settlement date determined via HOSE active trading sessions (`np.searchsorted` over actual business dates). Multiple tranches stopped out on the same date are consolidated into a single emergency liquidation episode (`stop_episodes`).

### Rule 6 — Period-End Inventory Mark-to-Market Accounting (`A-4`)
At the conclusion of each evaluation split, open positions are marked to market at the closing price of the final 30-minute bar. Unrealized profit/loss is reported explicitly alongside cash balances, avoiding artificial forced liquidations.

---

## 4. Backtesting on In-Sample Data (2021–2023)

- **Window**: `2021-01-01` to `2023-12-31` (3.0 years, 192,886 bars).
- **Market Context**: Encompasses the 2021 liquidity boom followed by the severe 2022 market decline where the VN30 index plunged by $-42.46\%$.

```bash
python run_is.py
```

### In-Sample Verified Performance

| Metric | Plutus Expected | Verified Result | Plutus Tolerance | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Total Return (HPR)** | $+2.79\%$ | **$+2.79\%$** ($+27,922,585\text{ VND}$) | Relative $\pm 5.0\%$ | **PASS** |
| **Annualized Return (CAGR)** | $+1.02\%$ | **$+1.02\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Maximum Drawdown (MDD)** | $-3.85\%$ | **$-3.85\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Daily Sharpe ($R_f=6\%$)** | $-1.510$ | **$-1.510$** | Absolute $\pm 0.15$ | **PASS** |
| **Calmar Ratio** | $0.265$ | **$0.265$** | Absolute $\pm 0.05$ | **PASS** |
| **VN30 Benchmark Return** | $-11.42\%$ | **$-11.42\%$** | — | **$+14.21\%$ Excess** |
| **VN30 Benchmark MaxDD** | $-42.46\%$ | **$-42.46\%$** | — | **$11\times$ Capital Protection** |
| **Market Beta ($\beta$)** | — | **$0.083$** | — | **Ultra-Low Beta** |
| **Completed Trades** | $767$ | **$767$** ($514$ TP, $253$ Rotation) | Relative $\pm 5.0\%$ | **PASS** |
| **Win Rate** | $67.0\%$ | **$67.0\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Emergency Floor Stops** | $0$ | **$0$ episodes ($0$ lots)** | Exact Match | **PASS** |
| **Period-End Inventory** | $0\text{ VND}$ | **$0\text{ VND}$ ($100\%$ Cash)** | Exact Match | **PASS** |

![In-Sample Equity Curve](images/equity_curve_in_sample.png)
*Figure 1: In-Sample Equity Curve (2021–2023) overlaid with normalized VN30 Benchmark equity line, demonstrating capital preservation during the 2022 crash.*

---

## 5. Hyperparameter Optimization & Sensitivity Analysis

### Exhaustive 25-Point In-Sample Grid Search (`P-1`, `P-2`, `P-6`)
To maintain time-series integrity, optimization was conducted **strictly on In-Sample data (2021–2023)** across all combinations of $N \in [14, 16, 18, 20, 22]$ and $\Delta \in [1.4\%, 1.6\%, 1.8\%, 2.0\%, 2.2\%]$. The objective function targeted the Calmar Ratio to prioritize drawdown containment over turnover.

```bash
python run_optimization.py
```

The full 25-point optimization surface is committed to [`results/optimization_grid_surface.csv`](file:///Users/ttt/Final_Projects_v1/strategies/minimalist_er_grid/results/optimization_grid_surface.csv).

#### Full Surface: In-Sample Calmar Ratio Matrix

| Levels ($N$) \ Spacing ($\Delta$) | 1.4% | 1.6% | 1.8% | 2.0% | 2.2% |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **$N = 14$** | $-0.247$ | $-0.096$ | $+0.025$ | $+0.125$ | $+0.239$ |
| **$N = 16$** | $-0.182$ | $-0.046$ | $+0.030$ | $+0.138$ | **$+0.265$ (Global Optimum)** |
| **$N = 18$** | $-0.194$ | $-0.035$ | $+0.031$ | $+0.143$ | $+0.263$ |
| **$N = 20$** | $-0.147$ | $-0.058$ | $+0.008$ | $+0.110$ | $+0.229$ |
| **$N = 22$** | $-0.171$ | $-0.090$ | $-0.023$ | $+0.071$ | $+0.182$ |

#### Full Surface: In-Sample Daily Sharpe Ratio Matrix

| Levels ($N$) \ Spacing ($\Delta$) | 1.4% | 1.6% | 1.8% | 2.0% | 2.2% |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **$N = 14$** | $-1.367$ | $-1.242$ | $-1.215$ | $-1.239$ | $-1.264$ |
| **$N = 16$** | $-1.376$ | $-1.334$ | $-1.417$ | $-1.466$ | $-1.510$ |
| **$N = 18$** | $-1.560$ | $-1.505$ | $-1.615$ | $-1.692$ | $-1.760$ |
| **$N = 20$** | $-1.617$ | $-1.715$ | $-1.853$ | $-1.944$ | $-2.034$ |
| **$N = 22$** | $-1.815$ | $-1.942$ | $-2.098$ | $-2.235$ | $-2.329$ |

**Optimal Parameter Selection**: The global optimum **$N = 16$ levels, $\Delta = 2.2\%$** achieved Calmar Ratio $+0.265$, HPR $+2.79\%$, and Max Drawdown $-3.85\%$, committed to [`config/best_params.yaml`](file:///Users/ttt/Final_Projects_v1/strategies/minimalist_er_grid/config/best_params.yaml) and automatically loaded by all downstream runners.

---

### In-Sample Lookback $\times$ Rebalance Sensitivity Sweep (`P-1`)
To examine sensitivity to selection timing, an exhaustive 16-combination sweep across lookback $\in [20, 30, 40, 60]\text{ days}$ and rebalance $\in [5, 10, 15, 20]\text{ days}$ was executed strictly on In-Sample data:

```bash
python sweep_lookback_rebalance.py
```

Saved to [`results/lookback_rebalance_surface.csv`](file:///Users/ttt/Final_Projects_v1/strategies/minimalist_er_grid/results/lookback_rebalance_surface.csv):

#### In-Sample Total Return Matrix (%)

| Lookback \ Rebalance | 5 Days | 10 Days | 15 Days | 20 Days |
| :--- | :---: | :---: | :---: | :---: |
| **20 Days** | $+2.63\%$ | $+0.34\%$ | $+7.86\%$ | $+4.59\%$ |
| **30 Days** | $+5.93\%$ | $+6.83\%$ | $+7.85\%$ | $-6.33\%$ |
| **40 Days** | $+4.03\%$ | $+0.44\%$ | $+2.61\%$ | $+3.82\%$ |
| **60 Days** | $+1.31\%$ | $+1.10\%$ | $-1.24\%$ | $-9.15\%$ |

#### In-Sample Max Drawdown Matrix (%)

| Lookback \ Rebalance | 5 Days | 10 Days | 15 Days | 20 Days |
| :--- | :---: | :---: | :---: | :---: |
| **20 Days** | $-4.00\%$ | $-6.34\%$ | $-4.46\%$ | $-5.11\%$ |
| **30 Days** | $-2.58\%$ | $-3.19\%$ | $-3.38\%$ | $-14.83\%$ |
| **40 Days** | $-3.70\%$ | $-5.17\%$ | $-7.02\%$ | $-5.97\%$ |
| **60 Days** | $-7.88\%$ | $-5.73\%$ | $-6.26\%$ | $-18.95\%$ |

---

## 6. Backtesting on Out-of-Sample Data (2024)

- **Window**: `2024-01-01` to `2024-12-31` (1.0 year, 67,428 bars).
- **Parameters**: Piped from `config/best_params.yaml` ($N=16, \Delta=2.2\%$) with 40-day warm-up.

```bash
python run_oos.py
```

### Out-of-Sample Verified Performance

| Metric | Plutus Expected | Verified Result | Plutus Tolerance | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Total Return (HPR)** | $+5.59\%$ | **$+5.59\%$** ($+55,885,787\text{ VND}$) | Relative $\pm 5.0\%$ | **PASS** |
| **Annualized Return (CAGR)** | $+5.60\%$ | **$+5.60\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Maximum Drawdown (MDD)** | $-0.91\%$ | **$-0.91\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Daily Sharpe ($R_f=6\%$)** | $-0.247$ | **$-0.247$** | Absolute $\pm 0.15$ | **PASS** |
| **Calmar Ratio** | $6.153$ | **$6.153$** | Relative $\pm 5.0\%$ | **PASS** |
| **VN30 Benchmark Return** | $+18.83\%$ | **$+18.83\%$** | — | — |
| **Market Beta ($\beta$)** | — | **$0.045$** | — | **Market Neutral** |
| **Completed Trades** | $200$ | **$200$** ($149$ TP, $51$ Rotation) | Relative $\pm 5.0\%$ | **PASS** |
| **Win Rate** | $74.5\%$ | **$74.5\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Emergency Floor Stops** | $0$ | **$0$ episodes ($0$ lots)** | Exact Match | **PASS** |
| **Period-End Inventory** | — | **POW: $3,000$ shs ($29.76\text{M VND}$, unrealized $-176\text{k}$)** | — | Marked to Market |

![Out-of-Sample Equity Curve](images/equity_curve_out_sample.png)
*Figure 2: Out-of-Sample Equity Curve (2024) showing stable equity growth with near-zero drawdown ($-0.91\%$).*

---

## 7. 2025 Bull Regime Evaluation (`P-3`)

- **Window**: `2025-01-01` to `2025-12-31` (1.0 year, 66,244 bars).
- **Macroeconomic Regime**: Strong liquidity bull market. The VN30 index surged by **$+51.18\%$** with a $-16.22\%$ intra-year correction.

```bash
python run_2025.py
```

### 2025 Bull Regime Verified Performance

| Metric | Verified Value | Macro Context |
| :--- | :---: | :---: |
| **Holding Period Return (HPR)** | **$+8.57\%$** ($+85,725,956\text{ VND}$) | Consistent absolute cash harvest |
| **Annualized Return (CAGR)** | **$+8.62\%$** | Exceeds risk-free rate ($6.0\%$) |
| **Maximum Drawdown (MDD)** | **$-3.38\%$** | $5\times$ lower than VN30 ($-16.22\%$) |
| **Daily Sharpe ($R_f=6\%$)** | **$+0.543$** | Positive risk-adjusted excess return |
| **Calmar Ratio** | **$2.549$** | High drawdown efficiency |
| **VN30 Benchmark Return** | **$+51.18\%$** | Parabolic trend market |
| **Market Beta ($\beta$)** | **$0.125$** | Low systematic equity correlation |
| **Completed Trades** | **$329$** ($262$ TP, $67$ Rotation) | $79.6\%$ Win Rate |
| **Period-End Open Inventory** | **GVR: $2,100$ shs ($55.02\text{M VND}$)** | Unrealized $-1.31\text{M VND}$ |

### Empirical Insights on Grid Mechanics in Bull Markets
During a directional bull regime, spot grid trading intentionally underperforms pure long equity buy-and-hold because:
1. Long tranches are progressively liquidated into take-profit targets as prices rise, converting stock equity into risk-free cash.
2. The portfolio holds an average cash reserve of $60\% - 85\%$, damping volatility and keeping market beta low ($\beta = 0.125$).
3. In exchange for conceding market beta in parabolic runs, the strategy limits drawdowns to $-3.38\%$ (compared to $-16.22\%$ for the index).

![2025 Bull Regime Equity Curve](images/equity_curve_2025.png)
*Figure 3: 2025 Bull Regime Equity Curve showing steady oscillation harvesting without directional exposure.*

---

## 8. Paper Trading & Forward Holdout Evaluation (2026)

- **Window**: `2026-01-01` to `2026-09-18` (8.5 months / 174 trading sessions / 256 calendar days, 46,203 bars).
- **Macroeconomic Regime**: Choppy market with downward drift. The VN30 index fell by **$-3.18\%$** with a **$-16.96\%$** maximum drawdown.

```bash
python run_holdout.py
```

### Forward Holdout Verified Performance

| Metric | Plutus Expected | Verified Result | Plutus Tolerance | Status |
| :--- | :---: | :---: | :---: | :---: |
| **Total Return (HPR)** | $+5.37\%$ | **$+5.37\%$** ($+53,661,064\text{ VND}$) | Relative $\pm 5.0\%$ | **PASS** |
| **Annualized Return (CAGR)** | $+7.74\%$ | **$+7.74\%$** (Annualized rate over 256 days) | Relative $\pm 5.0\%$ | **PASS** |
| **Maximum Drawdown (MDD)** | $-2.13\%$ | **$-2.13\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Daily Sharpe ($R_f=6\%$)** | $+0.431$ | **$+0.431$** | Absolute $\pm 0.15$ | **PASS** |
| **Calmar Ratio** | $3.639$ | **$3.639$** | Relative $\pm 5.0\%$ | **PASS** |
| **VN30 Benchmark Return** | $-3.18\%$ | **$-3.18\%$** | — | **$+8.55\%$ Alpha Excess** |
| **VN30 Benchmark MaxDD** | $-16.96\%$ | **$-16.96\%$** | — | **$8\times$ Drawdown Reduction** |
| **Market Beta ($\beta$)** | — | **$0.094$** | — | **Market Neutral** |
| **Completed Trades** | $248$ | **$248$** ($192$ TP, $56$ Rotation) | Relative $\pm 5.0\%$ | **PASS** |
| **Win Rate** | $77.4\%$ | **$77.4\%$** | Relative $\pm 5.0\%$ | **PASS** |
| **Emergency Floor Stops** | $0$ | **$0$ episodes ($0$ lots)** | Exact Match | **PASS** |
| **Period-End Inventory** | — | **GVR: $400$, TCB: $400$, VHM: $400$ ($53.8\text{M}$)** | — | Unrealized $+554\text{k VND}$ |

> [!NOTE]
> **Mathematical Clarification on Annualized Return (CAGR: $+7.74\%$) vs. Total Return (HPR: $+5.37\%$)**:
> Annualized return normalizes returns to a standard 365.25-day annual basis:
> 
> $$\text{CAGR} = (1 + \text{HPR})^{\frac{365.25}{\text{Days}}} - 1$$
> 
> Because the Forward Holdout spans **256.0 calendar days (0.701 years)**, the compounding factor is $\frac{365.25}{256.0} \approx 1.4267$. Generating $+5.37\%$ in 8.5 months yields an annualized rate of $(1 + 0.0537)^{1.4267} - 1 = \mathbf{+7.74\%}$.

![Forward Holdout Equity Curve](images/equity_curve_holdout.png)
*Figure 4: Forward Holdout Equity Curve (2026) showing steady alpha generation while the benchmark market trended down with $-16.96\%$ drawdown.*

---

## 9. Advanced Research & Empirical Studies

### 1. Visualizing the Grid Over Candlestick Price Action
To verify limit order execution against actual HOSE 30-minute bar prints, [`visualize_price_grid_overlay.py`](file:///Users/ttt/Final_Projects_v1/strategies/minimalist_er_grid/visualize_price_grid_overlay.py) generates a candlestick overlay:

```bash
python visualize_price_grid_overlay.py
```

![Grid Price Overlay](images/grid_price_overlay_demonstration.png)
*Figure 5: High-resolution candlestick grid overlay showing 50-SMA anchor, geometric buy limit orders, take-profit executions, and rotation liquidations.*

### 2. Empirical Validation of Kaufman ER: Oscillation vs. Trend
To verify that Low ER stocks complete more profitable roundtrips than High ER stocks under identical grid spacing, [`analyze_er_roundtrips.py`](file:///Users/ttt/Final_Projects_v1/strategies/minimalist_er_grid/analyze_er_roundtrips.py) compares roundtrip completion rates across VN30 constituents:

```bash
python analyze_er_roundtrips.py
```

![ER Roundtrip Comparison](images/er_roundtrip_comparison.png)
*Figure 6: Empirical proof that Low ER stocks execute significantly more take-profit roundtrips with lower inventory accumulation than High ER stocks.*

---

## Reproduction & Step-by-Step Execution Guide

### 1. Environment Setup
```bash
git clone https://github.com/Tathao1t1/Minimalist_ER_Grid.git
cd Minimalist_ER_Grid

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Running Individual Steps
Each pipeline step is executable standalone:

```bash
# Step 2: Data preparation and checksum validation
python run_data_prep.py

# Step 4: In-Sample evaluation (2021-2023)
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
```

### 3. Containerized Verification via Plutus
Reproduce the pipeline inside an isolated container with `plutus-verify`:

```bash
plutus-verify check .
```

---

## Directory Structure

```text
strategies/minimalist_er_grid/
├── README.md                           # Comprehensive quantitative research documentation
├── requirements.txt                    # Pinned package dependencies
├── .plutus/
│   ├── manifest.yaml                   # PLUTUS reproducibility manifest (v2.0)
│   └── expected/                       # Baseline verified metrics and visual artifacts
├── config/
│   ├── config.yaml                     # Strategy base configuration
│   └── best_params.yaml                # Optimal parameters (N=16, spacing=0.022) piped from IS grid search
├── src/
│   ├── logic.py                        # Execution engine with T+2 settlement, 50 bps fees, and rotation rules
│   ├── data_fetcher.py                 # Multi-split loader with 40-day indicator pre-split warm-up
│   └── optimizer.py                    # Exhaustive 25-point In-Sample grid search engine
├── run_data_prep.py                    # Step 2: Data preparation & split checksum verification
├── run_is.py                           # Step 4: In-Sample evaluation runner (2021–2023)
├── run_optimization.py                 # Step 5: Parameter optimization runner (In-Sample grid)
├── run_oos.py                          # Step 6: Out-of-Sample evaluation runner (2024)
├── run_2025.py                         # Step 7a: 2025 Bull Regime evaluation runner
├── run_holdout.py                      # Step 7b: Forward blind holdout runner (2026)
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

## References

1. **Perry J. Kaufman (2013)**. *Trading Systems and Methods*, 5th Edition. John Wiley & Sons.
2. **State Securities Commission of Vietnam (SSC)**. *Circular No. 120/2020/TT-BTC on Trading Regulations for Listed Securities on HOSE*. Ministry of Finance of Vietnam.
3. **Algotrade Plutus Quantitative Standard (2025)**. *Guidelines for Reproducible Quantitative Research and The 9-Step Strategy Development Lifecycle*.
4. **Algotrade Education (2025)**. *Dynamic Grid Trading Algorithm - Project of Group 5 - CS408 - APCS, HCMUS*. GitHub: [algotrade-education/DynamicGrid](https://github.com/algotrade-education/DynamicGrid).
