import os
import sys
import yaml

curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from src.data_fetcher import prepare_data
from src.logic import MinimalistERGridBacktest

def main():
    print("=" * 70)
    print("MINIMALIST ER SPOT GRID — OUT-OF-SAMPLE EVALUATION (2024)")
    print("=" * 70)
    
    cfg_path = os.path.join(curr_dir, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
        
    strat_cfg = config.get("strategy", {})
    bundle = prepare_data(config, "out_sample")
    
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
        trend_filter=strat_cfg.get("trend_filter", "none")
    )
    
    res = sim.backtest(bundle)
    print(f"Total Return (HPR): {res['hpr']:+.2f}% ({res['net_profit']:+,.0f} VND)")
    print(f"Annual Return:      {res['annual_return']:+.2f}%")
    print(f"Max Drawdown:       {res['max_drawdown']:.2f}%")
    print(f"Sharpe Ratio:       {res['sharpe_ratio']:.3f}")
    print(f"Calmar Ratio:       {res['calmar_ratio']:.3f}")
    print(f"Spot Harvest PnL:   {res['spot_harvest_pnl']:+,.0f} VND (TP Trades: {res['tp_trades']})")
    print(f"Spot Drag PnL:      {res['spot_drag_pnl']:+,.0f} VND (Floor Stops: {res['drag_trades']})")
    print(f"Total Trades:       {res['total_trades']} (Win Rate: {res['win_rate']:.1f}%)")
    print("=" * 70)

if __name__ == "__main__":
    main()
