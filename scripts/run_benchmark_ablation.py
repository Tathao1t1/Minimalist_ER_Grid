import os
import sys
import yaml
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
curr_dir = repo_root

from src.data_fetcher import prepare_data
from src.logic import MinimalistERGridBacktest

def load_deployed_params():
    """Pipes deployed hyperparameters from config/best_params.yaml."""
    best_params_path = os.path.join(curr_dir, "config/best_params.yaml")
    if os.path.exists(best_params_path):
        with open(best_params_path, "r") as f:
            best_cfg = yaml.safe_load(f)
        strat = best_cfg.get("strategy", {})
        return {
            "selection_lookback": strat.get("selection_lookback", 30),
            "selection_rebalance_days": strat.get("selection_rebalance_days", 15),
            "n_levels": strat.get("n_levels", 16),
            "grid_spacing_pct": strat.get("grid_spacing_pct", 0.020)
        }
    return {
        "selection_lookback": 30,
        "selection_rebalance_days": 15,
        "n_levels": 16,
        "grid_spacing_pct": 0.020
    }

def run_experiment(name, bundle, strat_cfg, **kwargs):
    sim = MinimalistERGridBacktest(
        capital=strat_cfg.get("capital", 1_000_000_000),
        initial_spot_capital=strat_cfg.get("initial_spot_capital", 1_000_000_000),
        broker_fee=strat_cfg.get("broker_fee", 0.0015),
        sell_tax=strat_cfg.get("sell_tax", 0.0010),
        slippage=strat_cfg.get("slippage", 0.0005),
        selection_lookback=strat_cfg.get("selection_lookback", 30),
        selection_rebalance_days=strat_cfg.get("selection_rebalance_days", 15),
        top_k=strat_cfg.get("top_k", 4),
        n_levels=strat_cfg.get("n_levels", 16),
        grid_spacing_pct=strat_cfg.get("grid_spacing_pct", 0.020),
        stop_buffer_levels=strat_cfg.get("stop_buffer_levels", 2),
        trend_filter=strat_cfg.get("trend_filter", "none"),
        risk_free_rate=strat_cfg.get("risk_free_rate", 0.06),
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
    
    # Pipe deployed parameters from config/best_params.yaml
    deployed_params = load_deployed_params()
    strat_cfg.update(deployed_params)
    print(f"Piping deployed parameters: lookback={strat_cfg['selection_lookback']}d, "
          f"rebalance={strat_cfg['selection_rebalance_days']}d, n_levels={strat_cfg['n_levels']}, "
          f"spacing={strat_cfg['grid_spacing_pct']:.3f}")
    
    splits = ["in_sample", "out_sample", "holdout"]
    
    all_results = []
    split_random_stats = {}
    
    for split in splits:
        print(f"\n---> Evaluating Split: {split.upper()} ...")
        bundle = prepare_data(config, split)
        
        # 1. Low ER (Proposed Strategy)
        res_low = run_experiment("Low ER (Proposed Strategy)", bundle, strat_cfg, selection_mode="er_low", use_sma_filter=True)
        all_results.append({
            "split": split,
            "cohort": "Low ER (Proposed Strategy)",
            "hpr": res_low["hpr"],
            "net_profit": res_low["net_profit"],
            "sharpe": res_low["daily_sharpe"],
            "max_dd": res_low["max_drawdown"],
            "win_rate": res_low["win_rate"],
            "tp_trades": res_low.get("tp_trades", 0),
            "stop_trades": res_low.get("stop_trades", 0),
            "harvest_pnl": res_low.get("spot_harvest_pnl", 0.0),
            "stop_pnl": res_low.get("floor_stop_pnl", 0.0),
            "rotation_pnl": res_low.get("rotation_pnl", 0.0),
            "equity_series": res_low["equity_series"]
        })
        print(f"  [Low ER (Proposed)]           HPR: {res_low['hpr']:+6.2f}% | Daily Sharpe: {res_low['daily_sharpe']:5.3f} | MaxDD: {res_low['max_drawdown']:5.2f}% | WinRate: {res_low['win_rate']:5.1f}%")
        
        # 2. High ER (Counter-Hypothesis)
        res_high = run_experiment("High ER (Counter-Hypothesis)", bundle, strat_cfg, selection_mode="er_high", use_sma_filter=True)
        all_results.append({
            "split": split,
            "cohort": "High ER (Counter-Hypothesis)",
            "hpr": res_high["hpr"],
            "net_profit": res_high["net_profit"],
            "sharpe": res_high["daily_sharpe"],
            "max_dd": res_high["max_drawdown"],
            "win_rate": res_high["win_rate"],
            "tp_trades": res_high.get("tp_trades", 0),
            "stop_trades": res_high.get("stop_trades", 0),
            "harvest_pnl": res_high.get("spot_harvest_pnl", 0.0),
            "stop_pnl": res_high.get("floor_stop_pnl", 0.0),
            "rotation_pnl": res_high.get("rotation_pnl", 0.0),
            "equity_series": res_high["equity_series"]
        })
        print(f"  [High ER (Counter-Hypothesis)] HPR: {res_high['hpr']:+6.2f}% | Daily Sharpe: {res_high['daily_sharpe']:5.3f} | MaxDD: {res_high['max_drawdown']:5.2f}% | WinRate: {res_high['win_rate']:5.1f}%")
        
        # 3. Low ER without SMA Filter
        res_nosma = run_experiment("Low ER without SMA Filter", bundle, strat_cfg, selection_mode="er_low", use_sma_filter=False)
        all_results.append({
            "split": split,
            "cohort": "Low ER without SMA Filter",
            "hpr": res_nosma["hpr"],
            "net_profit": res_nosma["net_profit"],
            "sharpe": res_nosma["daily_sharpe"],
            "max_dd": res_nosma["max_drawdown"],
            "win_rate": res_nosma["win_rate"],
            "tp_trades": res_nosma.get("tp_trades", 0),
            "stop_trades": res_nosma.get("stop_trades", 0),
            "harvest_pnl": res_nosma.get("spot_harvest_pnl", 0.0),
            "stop_pnl": res_nosma.get("floor_stop_pnl", 0.0),
            "rotation_pnl": res_nosma.get("rotation_pnl", 0.0),
            "equity_series": res_nosma["equity_series"]
        })
        print(f"  [Low ER without SMA Filter]   HPR: {res_nosma['hpr']:+6.2f}% | Daily Sharpe: {res_nosma['daily_sharpe']:5.3f} | MaxDD: {res_nosma['max_drawdown']:5.2f}% | WinRate: {res_nosma['win_rate']:5.1f}%")
        
        # 4. Random Selection across 20 distinct seeds
        print(f"  Evaluating Random Selection across 20 seeds (1..20)...")
        r_hprs, r_sharpes, r_mdds, r_winrates, r_stops, r_harvests, r_stop_pnls, r_rot_pnls = [], [], [], [], [], [], [], []
        r_eqs = []
        for seed in range(1, 21):
            r_res = run_experiment(f"Random seed={seed}", bundle, strat_cfg, selection_mode="random", use_sma_filter=True, seed=seed)
            r_hprs.append(r_res["hpr"])
            r_sharpes.append(r_res["daily_sharpe"])
            r_mdds.append(r_res["max_drawdown"])
            r_winrates.append(r_res["win_rate"])
            r_stops.append(r_res.get("stop_trades", 0))
            r_harvests.append(r_res.get("spot_harvest_pnl", 0.0))
            r_stop_pnls.append(r_res.get("floor_stop_pnl", 0.0))
            r_rot_pnls.append(r_res.get("rotation_pnl", 0.0))
            r_eqs.append(r_res["equity_series"])
            
        r_hprs = np.array(r_hprs)
        r_mean_hpr = float(np.mean(r_hprs))
        r_min_hpr = float(np.min(r_hprs))
        r_max_hpr = float(np.max(r_hprs))
        r_mean_sharpe = float(np.mean(r_sharpes))
        r_mean_mdd = float(np.mean(r_mdds))
        r_mean_wr = float(np.mean(r_winrates))
        r_mean_stops = float(np.mean(r_stops))
        r_mean_harvest = float(np.mean(r_harvests))
        r_mean_stop_pnl = float(np.mean(r_stop_pnls))
        
        # Percentile rank of Low ER within the 20-seed distribution
        pct_rank = float((np.sum(r_hprs < res_low["hpr"]) + 0.5 * np.sum(r_hprs == res_low["hpr"])) / len(r_hprs) * 100.0)
        
        # Pick median equity curve for visualization
        median_idx = int(np.argsort(r_hprs)[len(r_hprs) // 2])
        median_eq = r_eqs[median_idx]
        
        split_random_stats[split] = {
            "mean": r_mean_hpr,
            "min": r_min_hpr,
            "max": r_max_hpr,
            "percentile_rank": pct_rank
        }
        
        all_results.append({
            "split": split,
            "cohort": f"Random Selection (20 Seeds: {r_mean_hpr:+.2f}%, [{r_min_hpr:+.2f}%, {r_max_hpr:+.2f}%])",
            "hpr": r_mean_hpr,
            "net_profit": r_mean_hpr * 1e7,
            "sharpe": r_mean_sharpe,
            "max_dd": r_mean_mdd,
            "win_rate": r_mean_wr,
            "tp_trades": int(np.mean([len(eq) for eq in r_eqs])),
            "stop_trades": int(round(r_mean_stops)),
            "harvest_pnl": r_mean_harvest,
            "stop_pnl": r_mean_stop_pnl,
            "rotation_pnl": float(np.mean(r_rot_pnls)),
            "equity_series": median_eq
        })
        print(f"  [Random Selection (20 Seeds)] Mean: {r_mean_hpr:+6.2f}% (Range: [{r_min_hpr:+.2f}%, {r_max_hpr:+.2f}%]) | Low ER Percentile Rank: {pct_rank:.1f}th")
        
    summary_df = pd.DataFrame(all_results)
    
    # Save comparison chart
    fig, axes = plt.subplots(1, 3, figsize=(21, 6.5), sharey=False)
    colors = {
        "Low ER (Proposed Strategy)": "#059669",      # Emerald Green
        "High ER (Counter-Hypothesis)": "#DC2626",    # Crimson Red
        "Low ER without SMA Filter": "#D97706"       # Amber
    }
    styles = {
        "Low ER (Proposed Strategy)": "-",
        "High ER (Counter-Hypothesis)": "--",
        "Low ER without SMA Filter": "-."
    }
    
    split_titles = {
        "in_sample": "In-Sample Secular Bear (2021–2023)",
        "out_sample": "Out-of-Sample (2024)",
        "holdout": "Forward Holdout (2026)"
    }
    
    for idx, split in enumerate(splits):
        ax = axes[idx]
        split_rows = summary_df[summary_df["split"] == split]
        for _, row in split_rows.iterrows():
            c_name = row["cohort"]
            eq = (row["equity_series"] / 1_000_000_000.0) * 100.0
            if "Random" in c_name:
                ax.plot(eq.index, eq.values, label=f"Random (20 seeds mean {row['hpr']:+.2f}%)", color="#4B5563", linestyle=":", linewidth=1.8)
            else:
                label_text = f"{c_name}: {row['hpr']:+.2f}% (DD {row['max_dd']:.1f}%)"
                ax.plot(eq.index, eq.values, label=label_text, color=colors.get(c_name, "#6B7280"), linestyle=styles.get(c_name, "-"), linewidth=1.8)
                
        ax.set_title(split_titles[split], fontsize=13, fontweight="bold", pad=10)
        ax.axhline(100.0, color="#9CA3AF", linestyle="--", alpha=0.6, linewidth=1)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.set_ylabel("Portfolio Equity (Normalized Base = 100)", fontsize=10)
        ax.legend(loc="best", fontsize=8.5, framealpha=0.92)
            
    plt.suptitle("Kaufman Efficiency Ratio (ER) & SMA Proximity Ablation Study", fontsize=15, fontweight="bold", y=1.02)
    plt.tight_layout()
    
    os.makedirs(os.path.join(curr_dir, "images"), exist_ok=True)
    out_img = os.path.join(curr_dir, "images/benchmark_ablation_comparison.png")
    plt.savefig(out_img, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"\nSaved comparison chart to: {out_img}")

    print("\n" + "=" * 105)
    print("EXACT MARKDOWN TABLE FOR README:")
    print("=" * 105)
    print("| Evaluation Split | Selection Cohort | Total Return (HPR) | Sharpe Ratio (Rf=6%) | Max Drawdown | Win Rate | Floor Stops | Spot Harvest PnL | Rotation PnL |")
    print("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
    for split in splits:
        split_name = {
            "in_sample": "**In-Sample**<br>*(2021–2023)*",
            "out_sample": "**Out-of-Sample**<br>*(2024)*",
            "holdout": "**Forward Holdout**<br>*(2026)*"
        }[split]
        s_rows = summary_df[summary_df["split"] == split]
        for row_idx, (_, r) in enumerate(s_rows.iterrows()):
            sp = split_name if row_idx == 0 else ""
            bold = "**" if "Proposed" in r["cohort"] else ""
            c_label = r["cohort"]
            print(f"| {sp} | {bold}{c_label}{bold} | {bold}{r['hpr']:+.2f}%{bold} | {bold}{r['sharpe']:.3f}{bold} | {bold}{r['max_dd']:.2f}%{bold} | {bold}{r['win_rate']:.1f}%{bold} | {bold}{r['stop_trades']}{bold} | {bold}{r['harvest_pnl']:+,.0f} VND{bold} | {bold}{r['rotation_pnl']:+,.0f} VND{bold} |")
        # Print random stats row
        st = split_random_stats[split]
        print(f"| | *Random Baseline Percentile Rank* | *Low ER: {st['percentile_rank']:.1f}th percentile* | *Random 20-seed range: [{st['min']:+.2f}%, {st['max']:+.2f}%]* | — | — | — | — | — |")
    print("=" * 105)

if __name__ == "__main__":
    main()
