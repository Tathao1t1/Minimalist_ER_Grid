#!/usr/bin/env python3
"""
ER Roundtrip & Oscillation Velocity Analysis
Directly addresses Advisor Feedback:
  "Nếu em làm rõ được số roundtrip (mua bán liên tục) ở nhóm ER cao và ER thấp thì sẽ hay hơn.
   roundtrip so cùng biên độ 1% hay gì đó..."

Compares:
  - Low ER (Mean-reverting)
  - High ER (Trending)
  - Random Selection (Baseline)
Across fixed spacings:
  - 1.0% (Tight Grid Oscillation)
  - 1.8% (Standard Grid Oscillation)
"""

import os
import sys
import yaml
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from src.data_fetcher import prepare_data
from src.logic import MinimalistERGridBacktest

def run_cohort_test(bundle, strat_cfg, selection_mode, spacing_pct, seed=42):
    sim = MinimalistERGridBacktest(
        capital=strat_cfg.get("capital", 1_000_000_000),
        initial_spot_capital=strat_cfg.get("initial_spot_capital", 1_000_000_000),
        broker_fee=strat_cfg.get("broker_fee", 0.0015),
        sell_tax=strat_cfg.get("sell_tax", 0.0010),
        slippage=strat_cfg.get("slippage", 0.0005),
        selection_lookback=strat_cfg.get("selection_lookback", 30),
        selection_rebalance_days=strat_cfg.get("selection_rebalance_days", 15),
        top_k=strat_cfg.get("top_k", 4),
        n_levels=strat_cfg.get("n_levels", 14),
        grid_spacing_pct=spacing_pct,
        stop_buffer_levels=strat_cfg.get("stop_buffer_levels", 2),
        trend_filter="none",
        risk_free_rate=0.06,
        selection_mode=selection_mode,
        use_sma_filter=True,
        seed=seed
    )
    res = sim.backtest(bundle)
    
    trades = sim.trades_df
    tp_trades = trades[trades["reason"] == "target"] if len(trades) > 0 else pd.DataFrame()
    stop_trades = trades[trades["reason"] != "target"] if len(trades) > 0 else pd.DataFrame()
    
    roundtrip_count = len(tp_trades)
    avg_hold_hours = (tp_trades["holding_days"] * 24.0).mean() if roundtrip_count > 0 else 0.0
    harvest_pnl = tp_trades["pnl"].sum() if roundtrip_count > 0 else 0.0
    stop_count = len(stop_trades)
    drag_pnl = stop_trades["pnl"].sum() if stop_count > 0 else 0.0
    
    return {
        "roundtrip_count": roundtrip_count,
        "avg_hold_hours": avg_hold_hours,
        "harvest_pnl": harvest_pnl,
        "stop_count": stop_count,
        "drag_pnl": drag_pnl,
        "total_trades": len(trades),
        "win_rate": (roundtrip_count / len(trades) * 100.0) if len(trades) > 0 else 0.0,
        "hpr": res["hpr"],
        "max_dd": res["max_drawdown"],
        "sharpe": res["sharpe_ratio"],
        "equity_series": res["equity_series"],
        "tp_trades": tp_trades
    }

def main():
    print("=" * 90)
    print("EMPIRICAL ROUNDTRIP & OSCILLATION FREQUENCY ANALYSIS (LOW ER VS. HIGH ER VS. RANDOM)")
    print("Advisor Feedback Investigation: Proving ER identifies high-velocity oscillation assets")
    print("=" * 90)
    
    cfg_path = os.path.join(curr_dir, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
    strat_cfg = config.get("strategy", {})
    
    splits = ["in_sample", "out_sample", "holdout"]
    spacings = [0.010, 0.018]  # 1.0% and 1.8%
    cohorts = [
        ("Low ER (Proposed Strategy)", "er_low"),
        ("High ER (Counter-Hypothesis)", "er_high"),
        ("Random Selection (Baseline)", "random")
    ]
    
    records = []
    
    for split in splits:
        print(f"\n---> Evaluating Split: {split.upper()} ...")
        bundle = prepare_data(config, split)
        for sp in spacings:
            sp_label = f"{sp*100:.1f}% Spacing"
            print(f"  [Grid Spacing: {sp_label}]")
            for c_name, c_mode in cohorts:
                res = run_cohort_test(bundle, strat_cfg, c_mode, sp)
                records.append({
                    "split": split,
                    "spacing": sp_label,
                    "cohort": c_name,
                    "roundtrips": res["roundtrip_count"],
                    "avg_hold_hrs": res["avg_hold_hours"],
                    "harvest_pnl": res["harvest_pnl"],
                    "stops": res["stop_count"],
                    "drag_pnl": res["drag_pnl"],
                    "win_rate": res["win_rate"],
                    "hpr": res["hpr"],
                    "max_dd": res["max_dd"]
                })
                print(f"    {c_name:<30} | Roundtrips: {res['roundtrip_count']:>4} | Avg Hold: {res['avg_hold_hours']:4.1f}h | Harvest PnL: {res['harvest_pnl']/1e6:+6.1f}M | Stops: {res['stop_count']:>2}")
                
    df_res = pd.DataFrame(records)
    
    # Generate Visualization of Roundtrip Velocity & Harvest
    fig, axes = plt.subplots(2, 3, figsize=(20, 10), sharey=False)
    
    split_titles = {
        "in_sample": "In-Sample (2021–2023 Bear)",
        "out_sample": "Out-of-Sample (2024 Recovery)",
        "holdout": "Forward Holdout (2025–2026 Blind)"
    }
    
    palette = {
        "Low ER (Proposed Strategy)": "#059669",      # Green
        "High ER (Counter-Hypothesis)": "#DC2626",    # Red
        "Random Selection (Baseline)": "#4B5563"      # Gray
    }
    
    # Row 1: Completed Roundtrips (Trade Velocity)
    for idx, split in enumerate(splits):
        ax = axes[0, idx]
        sub = df_res[df_res["split"] == split]
        x_cats = ["1.0% Spacing", "1.8% Spacing"]
        x = np.arange(len(x_cats))
        width = 0.25
        
        for c_idx, (c_name, _) in enumerate(cohorts):
            vals = []
            for sp_l in x_cats:
                r = sub[(sub["cohort"] == c_name) & (sub["spacing"] == sp_l)]
                vals.append(r["roundtrips"].values[0] if len(r) > 0 else 0)
            ax.bar(x + (c_idx - 1) * width, vals, width, label=c_name, color=palette[c_name], alpha=0.9)
            for xi, vi in zip(x + (c_idx - 1) * width, vals):
                ax.text(xi, vi + max(vals)*0.02, str(vi), ha="center", fontsize=8.5, fontweight="bold")
                
        ax.set_title(f"{split_titles[split]}\nCompleted Roundtrips (Recycling Count)", fontsize=12, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(x_cats, fontsize=10, fontweight="bold")
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.set_ylabel("Number of Completed Roundtrips", fontsize=9.5)
        if idx == 0:
            ax.legend(loc="upper right", fontsize=8.5)
            
    # Row 2: Gross Harvest PnL (M VND)
    for idx, split in enumerate(splits):
        ax = axes[1, idx]
        sub = df_res[df_res["split"] == split]
        x_cats = ["1.0% Spacing", "1.8% Spacing"]
        x = np.arange(len(x_cats))
        width = 0.25
        
        for c_idx, (c_name, _) in enumerate(cohorts):
            vals = []
            for sp_l in x_cats:
                r = sub[(sub["cohort"] == c_name) & (sub["spacing"] == sp_l)]
                vals.append(r["harvest_pnl"].values[0] / 1e6 if len(r) > 0 else 0)
            ax.bar(x + (c_idx - 1) * width, vals, width, label=c_name, color=palette[c_name], alpha=0.9)
            for xi, vi in zip(x + (c_idx - 1) * width, vals):
                ax.text(xi, vi + max(vals)*0.02, f"{vi:+.0f}M", ha="center", fontsize=8.5, fontweight="bold")
                
        ax.set_title(f"Gross Harvest PnL (Million VND)", fontsize=12, fontweight="bold")
        ax.set_xticks(x)
        ax.set_xticklabels(x_cats, fontsize=10, fontweight="bold")
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.set_ylabel("Harvest Cash Flow (Million VND)", fontsize=9.5)
        
    plt.suptitle("Kaufman Efficiency Ratio (ER) Roundtrip Velocity & Harvest Cash Flow Analysis", fontsize=15, fontweight="bold", y=1.01)
    plt.tight_layout()
    
    os.makedirs(os.path.join(curr_dir, "images"), exist_ok=True)
    out_img = os.path.join(curr_dir, "images/er_roundtrip_comparison.png")
    plt.savefig(out_img, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\nSaved roundtrip comparison chart to: {out_img}")
    
    print("\n" + "=" * 110)
    print("ROUNDTRIP & HARVEST VELOCITY COMPARISON TABLE:")
    print("=" * 110)
    print(f"{'Split':<12} | {'Spacing':<12} | {'Cohort':<28} | {'Roundtrips':<11} | {'Avg Hold':<9} | {'Harvest PnL':<15} | {'Floor Stops':<11} | {'Drag PnL'}")
    print("-" * 110)
    for _, r in df_res.iterrows():
        print(f"{r['split']:<12} | {r['spacing']:<12} | {r['cohort']:<28} | {r['roundtrips']:>10}  | {r['avg_hold_hrs']:6.1f}h   | {r['harvest_pnl']/1e6:+9.1f}M VND  | {r['stops']:>10}  | {r['drag_pnl']/1e6:+9.1f}M VND")
    print("=" * 110)

if __name__ == "__main__":
    main()
