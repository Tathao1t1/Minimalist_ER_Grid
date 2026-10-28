import os
import yaml
import pandas as pd
import numpy as np
from .logic import MinimalistERGridBacktest
from .data_fetcher import prepare_data

def run_optimization(config):
    """
    Exhaustive 25-Point Grid Search Hyperparameter Optimization (P-1, P-2, P-6).
    Evaluates all combinations of N in [14, 16, 18, 20, 22] and Spacing in [1.4%, 2.2%]
    strictly on In-Sample (2021-2023) using institutional Daily Sharpe and Calmar Ratio.
    """
    data_bundle = prepare_data(config, "in_sample")
    opt_cfg = config.get("optimization", {})
    strat_cfg = config.get("strategy", {})
    strat_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    metric_target = opt_cfg.get("metric", "calmar_ratio")
    if metric_target in ("sharpe_ratio", "sharpe"):
        metric_target = "daily_sharpe"
        
    n_levels_list = [14, 16, 18, 20, 22]
    spacing_list = [0.014, 0.016, 0.018, 0.020, 0.022]
    
    print("=" * 80)
    print("EXHAUSTIVE 25-POINT IN-SAMPLE GRID SEARCH (2021-2023)")
    print(f"Target Optimization Metric: {metric_target.upper()}")
    print(f"{'Levels':<6} | {'Spacing':<8} | {'HPR (%)':<8} | {'MDD (%)':<8} | {'D-Sharpe':<8} | {'Calmar':<8} | {'TPs':<5} | {'Rot':<5}")
    print("-" * 80)
    
    surface_records = []
    
    for nl in n_levels_list:
        for sp in spacing_list:
            sim = MinimalistERGridBacktest(
                capital=strat_cfg.get("capital", 1_000_000_000),
                initial_spot_capital=strat_cfg.get("initial_spot_capital", 1_000_000_000),
                broker_fee=strat_cfg.get("broker_fee", 0.0015),
                sell_tax=strat_cfg.get("sell_tax", 0.0010),
                slippage=strat_cfg.get("slippage", 0.0005),
                selection_lookback=strat_cfg.get("selection_lookback", 40),
                selection_rebalance_days=strat_cfg.get("selection_rebalance_days", 10),
                top_k=strat_cfg.get("top_k", 4),
                n_levels=nl,
                grid_spacing_pct=sp,
                stop_buffer_levels=strat_cfg.get("stop_buffer_levels", 2),
                trend_filter=strat_cfg.get("trend_filter", "none"),
                risk_free_rate=strat_cfg.get("risk_free_rate", 0.06),
                use_sma_filter=True
            )
            res = sim.backtest(data_bundle)
            
            score = float(res.get(metric_target, res.get("calmar_ratio", 0.0)))
            surface_records.append({
                "n_levels": nl,
                "grid_spacing_pct": sp,
                "hpr": res["hpr"],
                "annual_return": res["annual_return"],
                "max_drawdown": res["max_drawdown"],
                "daily_sharpe": res["daily_sharpe"],
                "sharpe_30m": res["sharpe_ratio"],
                "calmar_ratio": res["calmar_ratio"],
                "total_trades": res["total_trades"],
                "tp_trades": res["tp_trades"],
                "rot_trades": res["rot_trades"],
                "score": score
            })
            print(f"{nl:<6} | {sp:<8.3f} | {res['hpr']:+6.2f}%  | {res['max_drawdown']:6.2f}%  | {res['daily_sharpe']:+6.3f}   | {res['calmar_ratio']:6.3f}   | {res['tp_trades']:<5} | {res['rot_trades']:<5}")
            
    df_surface = pd.DataFrame(surface_records)
    
    # Save full surface to results/optimization_grid_surface.csv
    results_dir = os.path.join(strat_dir, "results")
    os.makedirs(results_dir, exist_ok=True)
    surface_csv = os.path.join(results_dir, "optimization_grid_surface.csv")
    df_surface.to_csv(surface_csv, index=False)
    
    # Print Pivots for documentation & audit transparency
    print("\n" + "=" * 80)
    print("FULL SURFACE: IN-SAMPLE DAILY SHARPE RATIO")
    print("=" * 80)
    print(df_surface.pivot(index="n_levels", columns="grid_spacing_pct", values="daily_sharpe").round(3))
    
    print("\n" + "=" * 80)
    print("FULL SURFACE: IN-SAMPLE CALMAR RATIO")
    print("=" * 80)
    print(df_surface.pivot(index="n_levels", columns="grid_spacing_pct", values="calmar_ratio").round(3))
    
    # Select global optimal trial
    df_sorted = df_surface.sort_values(by=["score", "calmar_ratio", "daily_sharpe"], ascending=False).reset_index(drop=True)
    best_row = df_sorted.iloc[0]
    
    best_params = {
        "n_levels": int(best_row["n_levels"]),
        "grid_spacing_pct": float(round(best_row["grid_spacing_pct"], 4))
    }
    
    # Save to config/best_params.yaml for automated downstream piping (P-2, R-3)
    best_params_yaml = os.path.join(strat_dir, "config/best_params.yaml")
    with open(best_params_yaml, "w") as f:
        yaml.safe_dump({
            "strategy": {
                "n_levels": best_params["n_levels"],
                "grid_spacing_pct": best_params["grid_spacing_pct"]
            },
            "optimization_metadata": {
                "target_metric": metric_target,
                "best_value": float(round(best_row["score"], 4)),
                "in_sample_hpr": float(round(best_row["hpr"], 2)),
                "in_sample_mdd": float(round(best_row["max_drawdown"], 2)),
                "in_sample_daily_sharpe": float(round(best_row["daily_sharpe"], 3)),
                "in_sample_calmar": float(round(best_row["calmar_ratio"], 3))
            }
        }, f, sort_keys=False)
        
    print("\n" + "=" * 80)
    print("OPTIMAL IN-SAMPLE PARAMETERS (COMMITTED TO config/best_params.yaml):")
    print("=" * 80)
    print(f"n_levels:         {best_params['n_levels']}")
    print(f"grid_spacing_pct: {best_params['grid_spacing_pct']:.4f}")
    print(f"Objective ({metric_target}): {best_row['score']:.4f}")
    print(f"In-Sample HPR:    {best_row['hpr']:+.2f}%")
    print(f"In-Sample MDD:    {best_row['max_drawdown']:.2f}%")
    print(f"Surface CSV:      {surface_csv}")
    print("=" * 80)
    
    return best_params
