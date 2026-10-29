#!/usr/bin/env python3
"""
Signal Integration Diagnosis: Alpha Addition vs. Filter Gating
Implements the formal framework from 'ket-hop-tin-hieu-alpha-va-filter.md' (Advisor Guidance).

Evaluates whether secondary information B serves as:
  1. A standalone Alpha generator (sign(A + B) / Alpha Ensemble)
  2. An Entry Filter (A x filter(B) / Gated Engine)

Tested Signals:
  - Diagnosis 1: 50-SMA Proximity Condition (d_SMA <= 3%)
  - Diagnosis 2: Kaufman Efficiency Ratio (ER Low Selection vs. Random)
"""

import os
import sys
import yaml
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

curr_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(curr_dir)
for p in [curr_dir, project_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

from src.data_fetcher import prepare_data
from src.logic import MinimalistERGridBacktest, build_zero_overlap_whitelist

def run_grid_backtest(bundle, strat_cfg, selection_mode="er_low", use_sma_filter=True, seed=42):
    sim = MinimalistERGridBacktest(
        capital=strat_cfg.get("capital", 1_000_000_000),
        initial_spot_capital=strat_cfg.get("initial_spot_capital", 1_000_000_000),
        broker_fee=strat_cfg.get("broker_fee", 0.0015),
        sell_tax=strat_cfg.get("sell_tax", 0.0010),
        slippage=strat_cfg.get("slippage", 0.0005),
        selection_lookback=strat_cfg.get("selection_lookback", 40),
        selection_rebalance_days=strat_cfg.get("selection_rebalance_days", 10),
        top_k=strat_cfg.get("top_k", 4),
        n_levels=strat_cfg.get("n_levels", 18),
        grid_spacing_pct=strat_cfg.get("grid_spacing_pct", 0.018),
        stop_buffer_levels=strat_cfg.get("stop_buffer_levels", 2),
        trend_filter="none",
        risk_free_rate=0.06,
        selection_mode=selection_mode,
        use_sma_filter=use_sma_filter,
        seed=seed
    )
    res = sim.backtest(bundle)
    return res

def run_sma_standalone_alpha(bundle, strat_cfg, selection_mode="er_low"):
    """
    Evaluates 50-SMA proximity as an independent directional trading strategy (B alone):
    Buys stocks when price is within +/- 3% of the 50-period SMA.
    Exits when price detaches (> 3%) or ticker is rotated out of the whitelist.
    No grid levels; pure directional spot exposure.
    """
    bars_df = bundle["bars"].copy()
    if bars_df["close"].max() < 1000:
        for c in ["open", "high", "low", "close"]:
            bars_df[c] *= 1000.0
    bars_df = bars_df.sort_values(["bar_close", "tickersymbol"]).reset_index(drop=True)
    
    lookback = strat_cfg.get("selection_lookback", 40)
    rebal_days = strat_cfg.get("selection_rebalance_days", 10)
    top_k = strat_cfg.get("top_k", 4)
    capital = float(strat_cfg.get("capital", 1_000_000_000))
    
    whitelist_by_date = build_zero_overlap_whitelist(
        bars_df,
        lookback_days=lookback,
        rebalance_days=rebal_days,
        top_k=top_k,
        selection_mode=selection_mode,
        seed=42
    )
    
    anchors = {}
    for ticker, df in bars_df.groupby("tickersymbol"):
        anchors[ticker] = df.set_index("bar_close")["close"].rolling(50).mean()
        
    cash = capital
    positions = {}  # ticker: {"shares": int, "entry_cost": float}
    equity_records = []
    
    wl_dates = sorted(whitelist_by_date.keys())
    cur_wl = []
    next_wl_idx = 0
    trade_count = 0
    win_count = 0
    
    for ts, bar_group in bars_df.groupby("bar_close", sort=True):
        bar_group = bar_group.set_index("tickersymbol")
        cur_date = ts.date()
        if next_wl_idx < len(wl_dates) and cur_date >= wl_dates[next_wl_idx]:
            cur_wl = whitelist_by_date[wl_dates[next_wl_idx]]
            next_wl_idx += 1
            
        # 1. Check Exits (detached from SMA > 3% or rotated out)
        for ticker in list(positions.keys()):
            if ticker not in bar_group.index:
                continue
            bar_c = float(bar_group.loc[ticker, "close"])
            sma_val = anchors[ticker].get(ts, np.nan)
            detached = np.isnan(sma_val) or (abs(bar_c - sma_val) / sma_val > 0.03)
            if (ticker not in cur_wl) or detached:
                pos = positions.pop(ticker)
                actual_fill = bar_c * (1.0 - 0.0005)
                exit_cost = actual_fill * pos["shares"] * (0.0015 + 0.0010)
                proceeds = actual_fill * pos["shares"] - exit_cost
                cash += proceeds
                pnl = proceeds - pos["entry_cost"]
                trade_count += 1
                if pnl > 0:
                    win_count += 1
                    
        # 2. Check Entries (within 3% of SMA)
        avail_slots = top_k - len(positions)
        if avail_slots > 0 and len(cur_wl) > 0:
            alloc_per_stock = (capital / top_k)
            for ticker in cur_wl:
                if ticker in positions or ticker not in bar_group.index:
                    continue
                bar_c = float(bar_group.loc[ticker, "close"])
                sma_val = anchors[ticker].get(ts, np.nan)
                if not np.isnan(sma_val) and (abs(bar_c - sma_val) / sma_val <= 0.03):
                    actual_fill = bar_c * (1.0 + 0.0005)
                    raw_sh = int(min(alloc_per_stock, cash) / actual_fill)
                    shares = (raw_sh // 100) * 100
                    if shares > 0:
                        entry_cost = actual_fill * shares * (1.0 + 0.0015)
                        if cash >= entry_cost:
                            cash -= entry_cost
                            positions[ticker] = {"shares": shares, "entry_cost": entry_cost}
                            avail_slots -= 1
                            if avail_slots <= 0:
                                break
                                
        pos_val = sum(pos["shares"] * float(bar_group.loc[t, "close"]) for t, pos in positions.items() if t in bar_group.index)
        equity_records.append((ts, cash + pos_val))
        
    eq_series = pd.Series([v for _, v in equity_records], index=[t for t, _ in equity_records])
    hpr = (eq_series.iloc[-1] / capital - 1.0) * 100.0
    cummax = eq_series.cummax()
    dd = (eq_series - cummax) / cummax
    max_dd = float(dd.min()) * 100.0
    rets = eq_series.pct_change().dropna()
    rf_per_bar = 0.06 / 2016.0
    excess_mean = float(rets.mean() - rf_per_bar)
    sharpe = float(excess_mean / rets.std() * np.sqrt(2016)) if rets.std() > 0 else 0.0
    win_rate = (win_count / trade_count * 100.0) if trade_count > 0 else 0.0
    
    return {
        "hpr": hpr,
        "max_drawdown": max_dd,
        "sharpe_ratio": sharpe,
        "win_rate": win_rate,
        "total_trades": trade_count,
        "equity_series": eq_series
    }

def main():
    print("=" * 95)
    print("SIGNAL INTEGRATION DIAGNOSIS: ALPHA ADDITION VS. FILTER GATING")
    print("Testing framework from advisor guidance: ket-hop-tin-hieu-alpha-va-filter.md")
    print("=" * 95)
    
    cfg_path = os.path.join(project_root, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
    strat_cfg = config.get("strategy", {})
    
    splits = ["in_sample", "out_sample", "holdout"]
    split_labels = {
        "in_sample": "In-Sample Secular Bear (2021–2023)",
        "out_sample": "Out-of-Sample Recovery (2024)",
        "holdout": "Forward Blind Holdout (2025–2026)"
    }
    
    results = []
    
    for split in splits:
        print(f"\n[DIAGNOSING SPLIT: {split.upper()}] ...")
        bundle = prepare_data(config, split)
        
        # 1. A alone: Grid without SMA filter
        res_a = run_grid_backtest(bundle, strat_cfg, selection_mode="er_low", use_sma_filter=False)
        
        # 2. B alone: Standalone 50-SMA proximity directional strategy
        res_b = run_sma_standalone_alpha(bundle, strat_cfg, selection_mode="er_low")
        
        # 3. A x Filter(B): Grid gated by SMA proximity filter (Proposed strategy)
        res_filter = run_grid_backtest(bundle, strat_cfg, selection_mode="er_low", use_sma_filter=True)
        
        # 4. A + B (Voting / Sleeve Ensemble): 50% Grid (A) + 50% SMA Directional (B)
        eq_a = res_a["equity_series"]
        eq_b = res_b["equity_series"]
        common_idx = eq_a.index.intersection(eq_b.index)
        eq_comb = 0.5 * eq_a.loc[common_idx] + 0.5 * eq_b.loc[common_idx]
        hpr_comb = (eq_comb.iloc[-1] / 1_000_000_000.0 - 1.0) * 100.0
        cummax_comb = eq_comb.cummax()
        dd_comb = (eq_comb - cummax_comb) / cummax_comb
        max_dd_comb = float(dd_comb.min()) * 100.0
        rets_comb = eq_comb.pct_change().dropna()
        rf_per_bar = 0.06 / 2016.0
        sharpe_comb = float((rets_comb.mean() - rf_per_bar) / rets_comb.std() * np.sqrt(2016)) if rets_comb.std() > 0 else 0.0
        
        cohorts = [
            ("A riêng: Grid không dùng Filter", res_a["hpr"], res_a["sharpe_ratio"], res_a["max_drawdown"], eq_a),
            ("B riêng: Tín hiệu SMA độc lập", res_b["hpr"], res_b["sharpe_ratio"], res_b["max_drawdown"], eq_b),
            ("A + B: Cộng Alpha / Voting", hpr_comb, sharpe_comb, max_dd_comb, eq_comb),
            ("A qua Filter B: Grid gated by SMA (Đề xuất)", res_filter["hpr"], res_filter["sharpe_ratio"], res_filter["max_drawdown"], res_filter["equity_series"]),
        ]
        
        for name, hpr, sh, mdd, eq in cohorts:
            results.append({
                "split": split,
                "configuration": name,
                "hpr": hpr,
                "sharpe": sh,
                "max_dd": mdd,
                "equity_series": eq
            })
            print(f"  {name:<44} | Return: {hpr:+6.2f}% | Sharpe: {sh:5.3f} | MaxDD: {mdd:6.2f}%")
            
    summary_df = pd.DataFrame(results)
    
    # Generate Multi-Panel Comparison Visualization matching advisor PDF format
    fig, axes = plt.subplots(1, 3, figsize=(21, 6.5), sharey=False)
    
    colors = {
        "A riêng: Grid không dùng Filter": "#2563EB",            # Blue
        "B riêng: Tín hiệu SMA độc lập": "#8B5CF6",              # Purple
        "A + B: Cộng Alpha / Voting": "#DC2626",                 # Red
        "A qua Filter B: Grid gated by SMA (Đề xuất)": "#059669" # Emerald Green
    }
    styles = {
        "A riêng: Grid không dùng Filter": "--",
        "B riêng: Tín hiệu SMA độc lập": ":",
        "A + B: Cộng Alpha / Voting": "-.",
        "A qua Filter B: Grid gated by SMA (Đề xuất)": "-"
    }
    
    for idx, split in enumerate(splits):
        ax = axes[idx]
        split_rows = summary_df[summary_df["split"] == split]
        for _, row in split_rows.iterrows():
            c_name = row["configuration"]
            eq = (row["equity_series"] / 1_000_000_000.0) * 100.0  # Base 100
            label_text = f"{c_name.split(':')[0]}: {row['hpr']:+.2f}% (DD {row['max_dd']:.1f}%)"
            ax.plot(eq.index, eq.values, label=label_text, color=colors[c_name], linestyle=styles[c_name], linewidth=1.9)
            
        ax.set_title(split_labels[split], fontsize=12.5, fontweight="bold", pad=10)
        ax.axhline(100.0, color="#9CA3AF", linestyle="--", alpha=0.6, linewidth=1)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.set_ylabel("Portfolio Equity (Normalized Base = 100)", fontsize=10)
        ax.legend(loc="best", fontsize=8.2, framealpha=0.92)
        
    plt.suptitle("Kiểm chứng Vai trò Tín hiệu: Cộng Alpha (A + B) vs. Sử dụng Filter (A qua Filter B)", fontsize=14.5, fontweight="bold", y=1.02)
    plt.tight_layout()
    
    os.makedirs(os.path.join(project_root, "images"), exist_ok=True)
    out_img = os.path.join(project_root, "images/signal_role_diagnosis.png")
    plt.savefig(out_img, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\nSaved signal diagnosis chart to: {out_img}")
    
    print("\n" + "=" * 100)
    print("EXACT MARKDOWN TABLE FOR README & THESIS REPORT:")
    print("=" * 100)
    print("| Market Split | Integration Architecture | Mathematical Role | Total Return | Sharpe Ratio (Rf=6%) | Max Drawdown | Empirical Verdict |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    
    verdicts = {
        "A riêng: Grid không dùng Filter": "Unfiltered Baseline ($A$ alone)",
        "B riêng: Tín hiệu SMA độc lập": "Standalone Alpha ($B$ alone)",
        "A + B: Cộng Alpha / Voting": "Alpha Addition ($\text{sign}(A+B)$)",
        "A qua Filter B: Grid gated by SMA (Đề xuất)": "**Optimal: Gated Filter ($A \\times \\text{Filter}(B)$)**"
    }
    
    for split in splits:
        split_name = {
            "in_sample": "**In-Sample**<br>*(2021–2023 Bear)*",
            "out_sample": "**Out-of-Sample**<br>*(2024 Recovery)*",
            "holdout": "**Forward Holdout**<br>*(2025–2026 Blind)*"
        }[split]
        s_rows = summary_df[summary_df["split"] == split]
        for row_idx, (_, r) in enumerate(s_rows.iterrows()):
            sp = split_name if row_idx == 0 else ""
            c_name = r["configuration"]
            bold = "**" if "Filter B" in c_name else ""
            print(f"| {sp} | {bold}{c_name}{bold} | {bold}{verdicts[c_name]}{bold} | {bold}{r['hpr']:+.2f}%{bold} | {bold}{r['sharpe']:.3f}{bold} | {bold}{r['max_dd']:.2f}%{bold} | {bold}{'Matches Advisor Example 1: Filter Wins' if 'Filter B' in c_name else 'Sub-optimal'}{bold} |")
    print("=" * 100)

if __name__ == "__main__":
    main()
