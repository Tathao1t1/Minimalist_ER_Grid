#!/usr/bin/env python3
import sys, os, yaml
import pandas as pd
import numpy as np

curr_dir = os.path.dirname(os.path.abspath(__file__))
strat_dir = curr_dir
if strat_dir not in sys.path:
    sys.path.insert(0, strat_dir)

from src.data_fetcher import prepare_data
from src.logic import MinimalistERGridBacktest

cfg_path = os.path.join(strat_dir, "config/config.yaml")
with open(cfg_path, "r") as f:
    cfg = yaml.safe_load(f)

b_is = prepare_data(cfg, "in_sample")
b_ho = prepare_data(cfg, "holdout")

lookbacks = [20, 30, 40, 60]
rebalances = [5, 10, 15, 20]

results = []

print("Running Lookback x Rebalance Sensitivity Sweep...")
print(f"{'Lookback':<10} | {'Rebalance':<10} | {'IS Return':<12} | {'IS MaxDD':<10} | {'Holdout Ret':<12} | {'Holdout MaxDD':<14} | {'Holdout TPs'}")
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
        
        sim_ho = MinimalistERGridBacktest(
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
        res_ho = sim_ho.backtest(b_ho)
        
        results.append({
            "lookback": lb,
            "rebalance": rb,
            "is_ret": res_is["hpr"],
            "is_mdd": res_is["max_drawdown"],
            "is_sharpe": res_is["sharpe_ratio"],
            "ho_ret": res_ho["hpr"],
            "ho_mdd": res_ho["max_drawdown"],
            "ho_sharpe": res_ho["sharpe_ratio"],
            "ho_trades": res_ho["tp_trades"]
        })
        print(f"{lb:>4} days   | {rb:>4} days   | {res_is['hpr']:+6.2f}%     | {res_is['max_drawdown']:5.1f}%    | {res_ho['hpr']:+6.2f}%      | {res_ho['max_drawdown']:5.1f}%         | {res_ho['tp_trades']:>4}")

df = pd.DataFrame(results)

print("\n" + "=" * 65)
print("SENSITIVITY MATRIX: HOLDOUT TOTAL RETURN (%)")
print("=" * 65)
piv_ho_ret = df.pivot(index="lookback", columns="rebalance", values="ho_ret")
print(piv_ho_ret.round(2))

print("\n" + "=" * 65)
print("SENSITIVITY MATRIX: IN-SAMPLE CRASH TOTAL RETURN (%)")
print("=" * 65)
piv_is_ret = df.pivot(index="lookback", columns="rebalance", values="is_ret")
print(piv_is_ret.round(2))

print("\n" + "=" * 65)
print("SENSITIVITY MATRIX: HOLDOUT MAX DRAWDOWN (%)")
print("=" * 65)
piv_ho_mdd = df.pivot(index="lookback", columns="rebalance", values="ho_mdd")
print(piv_ho_mdd.round(2))
