#!/usr/bin/env python3
import sys, os, yaml
import pandas as pd
import numpy as np

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
strat_dir = repo_root
curr_dir = repo_root

from src.data_fetcher import prepare_data
from src.logic import MinimalistERGridBacktest

cfg_path = os.path.join(strat_dir, "config/config.yaml")
with open(cfg_path, "r") as f:
    cfg = yaml.safe_load(f)

# Protocol P-1: Evaluated strictly on In-Sample without forward data snooping
b_is = prepare_data(cfg, "in_sample")

lookbacks = [20, 30, 40, 60]
rebalances = [5, 10, 15, 20]

results = []

print("=" * 85)
print("IN-SAMPLE LOOKBACK x REBALANCE SENSITIVITY SWEEP (2021-2023)")
print("=" * 85)
print(f"{'Lookback':<10} | {'Rebalance':<10} | {'IS Return':<12} | {'IS MaxDD':<10} | {'D-Sharpe':<10} | {'Calmar':<10} | {'TP Trades':<10}")
print("-" * 85)

for lb in lookbacks:
    for rb in rebalances:
        sim_is = MinimalistERGridBacktest(
            capital=1e9,
            selection_lookback=lb,
            selection_rebalance_days=rb,
            top_k=4,
            n_levels=18,
            grid_spacing_pct=0.018,
            stop_buffer_levels=2,
            selection_mode="er_low",
            use_sma_filter=True,
            risk_free_rate=0.06
        )
        res_is = sim_is.backtest(b_is)
        
        results.append({
            "lookback": lb,
            "rebalance": rb,
            "is_ret": res_is["hpr"],
            "is_mdd": res_is["max_drawdown"],
            "is_d_sharpe": res_is["daily_sharpe"],
            "is_calmar": res_is["calmar_ratio"],
            "is_tp_trades": res_is["tp_trades"],
            "is_rot_trades": res_is["rot_trades"]
        })
        print(f"{lb:>4} days   | {rb:>4} days   | {res_is['hpr']:+6.2f}%     | {res_is['max_drawdown']:5.2f}%    | {res_is['daily_sharpe']:+6.3f}     | {res_is['calmar_ratio']:6.3f}     | {res_is['tp_trades']:>4}")

df = pd.DataFrame(results)

# Save to results/lookback_rebalance_surface.csv
os.makedirs(os.path.join(strat_dir, "results"), exist_ok=True)
csv_out = os.path.join(strat_dir, "results/lookback_rebalance_surface.csv")
df.to_csv(csv_out, index=False)

print("\n" + "=" * 65)
print("IN-SAMPLE SENSITIVITY MATRIX: TOTAL RETURN (%)")
print("=" * 65)
piv_ret = df.pivot(index="lookback", columns="rebalance", values="is_ret")
print(piv_ret.round(2))

print("\n" + "=" * 65)
print("IN-SAMPLE SENSITIVITY MATRIX: MAX DRAWDOWN (%)")
print("=" * 65)
piv_mdd = df.pivot(index="lookback", columns="rebalance", values="is_mdd")
print(piv_mdd.round(2))

print("\n" + "=" * 65)
print("IN-SAMPLE SENSITIVITY MATRIX: DAILY SHARPE RATIO")
print("=" * 65)
piv_sharpe = df.pivot(index="lookback", columns="rebalance", values="is_d_sharpe")
print(piv_sharpe.round(3))

print("\n" + "=" * 65)
print("IN-SAMPLE SENSITIVITY MATRIX: CALMAR RATIO")
print("=" * 65)
piv_calmar = df.pivot(index="lookback", columns="rebalance", values="is_calmar")
print(piv_calmar.round(3))
print("=" * 65)
print(f"Results saved to: {csv_out}\n")
