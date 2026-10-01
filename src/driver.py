import os
import sys
import argparse
import yaml
import pandas as pd
from datetime import datetime

curr_dir = os.path.dirname(os.path.abspath(__file__))
strat_dir = os.path.dirname(curr_dir)
if strat_dir not in sys.path:
    sys.path.insert(0, strat_dir)

from src.data_fetcher import prepare_data
from src.logic import MinimalistERGridBacktest
from src.optimizer import run_optimization

def run_backtest_pipeline(config, data_split="in_sample", output_dir=None):
    strat_cfg = config.get("strategy", {})
    data_bundle = prepare_data(config, data_split)
    
    backtester = MinimalistERGridBacktest(
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
        trend_filter=strat_cfg.get("trend_filter", "none")
    )
    
    results = backtester.backtest(data_bundle)
    
    print("\n" + "=" * 65)
    print(f"BACKTEST PERFORMANCE SUMMARY [{data_split.upper()}]")
    print("=" * 65)
    print(f"Total Trades:        {results['total_trades']}")
    print(f"Take-Profit Trades:  {results['tp_trades']} (Win Rate: {results['win_rate']:.1f}%)")
    print(f"Floor Stop Trades:   {results['drag_trades']}")
    print(f"Pure Grid Harvest:   {results['spot_harvest_pnl']:+,.0f} VND")
    print(f"Spot Downtrend Drag: {results['spot_drag_pnl']:+,.0f} VND")
    print(f"Net Profit:          {results['net_profit']:+,.0f} VND")
    print(f"Total Return (HPR):  {results['hpr']:+.2f}%")
    print(f"Annual Return:       {results['annual_return']:+.2f}%")
    print(f"Max Drawdown:        {results['max_drawdown']:.2f}%")
    print(f"Longest Drawdown:    {results['longest_dd_days']} days")
    print(f"Sharpe Ratio:        {results['sharpe_ratio']:.3f}")
    print(f"Sortino Ratio:       {results['sortino_ratio']:.3f}")
    print(f"Calmar Ratio:        {results['calmar_ratio']:.3f}")
    print(f"Final Capital:       {results['final_capital']:,.0f} VND")
    print("=" * 65)
    
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        if len(backtester.trades_df) > 0:
            backtester.trades_df.to_csv(os.path.join(output_dir, "trade_log.csv"), index=False)
        backtester.equity_series.to_csv(os.path.join(output_dir, "equity_series.csv"))
        print(f"Artifacts saved to {output_dir}")
        
    return results

def main():
    parser = argparse.ArgumentParser(description="Minimalist ER Grid Strategy Driver")
    parser.add_argument("--mode", choices=["backtest", "optimize"], default="backtest", help="Execution mode")
    parser.add_argument("--data", choices=["in_sample", "out_sample", "holdout"], default="in_sample", help="Data split")
    parser.add_argument("--config", default="config/config.yaml", help="Path to config file")
    args = parser.parse_args()
    
    cfg_path = args.config if os.path.isabs(args.config) else os.path.join(strat_dir, args.config)
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
        
    if args.mode == "backtest":
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(strat_dir, "results", "backtest", ts)
        run_backtest_pipeline(config, args.data, out_dir)
    elif args.mode == "optimize":
        run_optimization(config)

if __name__ == "__main__":
    main()
