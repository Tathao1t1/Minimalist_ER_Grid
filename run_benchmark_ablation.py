import os
import sys
import yaml
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from src.data_fetcher import prepare_data
from src.logic import MinimalistERGridBacktest

def run_experiment(name, bundle, strat_cfg, **kwargs):
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
        trend_filter=strat_cfg.get("trend_filter", "none"),
        **kwargs
    )
    res = sim.backtest(bundle)
    res["name"] = name
    return res

def main():
    print("=" * 80)
    print("PLUTUS ABLATION & BENCHMARK STUDY: KAUFMAN ER & SMA FILTER VALIDATION")
    print("=" * 80)
    
    cfg_path = os.path.join(curr_dir, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
    strat_cfg = config.get("strategy", {})
    
    # Evaluate across In-Sample (2021-2023) and Out-of-Sample (2024)
    splits = ["in_sample", "out_sample", "holdout"]
    
    experiments = [
        {"name": "Low ER (Proposed Strategy)", "selection_mode": "er_low", "use_sma_filter": True},
        {"name": "High ER (Counter-Hypothesis)", "selection_mode": "er_high", "use_sma_filter": True},
        {"name": "Random Selection (Baseline)", "selection_mode": "random", "use_sma_filter": True, "seed": 42},
        {"name": "Low ER without SMA Filter", "selection_mode": "er_low", "use_sma_filter": False},
    ]
    
    all_results = []
    
    for split in splits:
        print(f"\n---> Evaluating Split: {split.upper()} ...")
        bundle = prepare_data(config, split)
        for exp in experiments:
            res = run_experiment(exp["name"], bundle, strat_cfg, **{k: v for k, v in exp.items() if k != "name"})
            all_results.append({
                "split": split,
                "cohort": exp["name"],
                "hpr": res["hpr"],
                "net_profit": res["net_profit"],
                "sharpe": res["sharpe_ratio"],
                "max_dd": res["max_drawdown"],
                "win_rate": res["win_rate"],
                "tp_trades": res["tp_trades"],
                "drag_trades": res["drag_trades"],
                "harvest_pnl": res["spot_harvest_pnl"],
                "drag_pnl": res["spot_drag_pnl"],
                "equity_series": res["equity_series"]
            })
            print(f"  [{exp['name'][:30]:<30}] HPR: {res['hpr']:+6.2f}% | Sharpe: {res['sharpe_ratio']:5.3f} | MaxDD: {res['max_drawdown']:5.2f}% | WinRate: {res['win_rate']:5.1f}% | Stops: {res['drag_trades']}")
            
    summary_df = pd.DataFrame(all_results)
    
    print("\n" + "=" * 95)
    print(f"{'Split':<12} | {'Cohort':<32} | {'Return':<9} | {'Sharpe':<7} | {'MaxDD':<7} | {'WinRate':<7} | {'Stops'}")
    print("-" * 95)
    for _, row in summary_df.iterrows():
        print(f"{row['split']:<12} | {row['cohort']:<32} | {row['hpr']:+6.2f}%  | {row['sharpe']:6.3f} | {row['max_dd']:6.2f}% | {row['win_rate']:6.1f}% | {row['drag_trades']}")
    print("=" * 95)
    
    # Generate Multi-Panel Comparison Visualization
    fig, axes = plt.subplots(1, 3, figsize=(20, 6), sharey=False)
    colors = {
        "Low ER (Proposed Strategy)": "#059669",      # Emerald Green
        "High ER (Counter-Hypothesis)": "#DC2626",    # Crimson Red
        "Random Selection (Baseline)": "#4B5563",     # Slate Gray
        "Low ER without SMA Filter": "#D97706"       # Amber
    }
    styles = {
        "Low ER (Proposed Strategy)": "-",
        "High ER (Counter-Hypothesis)": "--",
        "Random Selection (Baseline)": ":",
        "Low ER without SMA Filter": "-."
    }
    
    split_titles = {
        "in_sample": "In-Sample Secular Bear (2021–2023)",
        "out_sample": "Out-of-Sample Recovery (2024)",
        "holdout": "Forward Blind Holdout (2025–2026)"
    }
    
    for idx, split in enumerate(splits):
        ax = axes[idx]
        split_rows = summary_df[summary_df["split"] == split]
        for _, row in split_rows.iterrows():
            c_name = row["cohort"]
            eq = (row["equity_series"] / 1_000_000_000.0) * 100.0  # Normalized to 100 base
            ax.plot(eq.index, eq.values, label=c_name, color=colors[c_name], linestyle=styles[c_name], linewidth=1.8)
            
        ax.set_title(split_titles[split], fontsize=13, fontweight="bold", pad=10)
        ax.axhline(100.0, color="#9CA3AF", linestyle="--", alpha=0.6, linewidth=1)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.set_ylabel("Portfolio Equity (Normalized Base = 100)", fontsize=10)
        if idx == 0:
            ax.legend(loc="lower left", fontsize=9, framealpha=0.9)
            
    plt.suptitle("Kaufman Efficiency Ratio (ER) & SMA Proximity Ablation Study", fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout()
    
    os.makedirs(os.path.join(curr_dir, "images"), exist_ok=True)
    out_img = os.path.join(curr_dir, "images/benchmark_ablation_comparison.png")
    plt.savefig(out_img, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\nSaved comparison chart to: {out_img}")

if __name__ == "__main__":
    main()
