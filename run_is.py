import os
import sys
import yaml

curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

try:
    import plutus_verify as pv
except ImportError:
    from contextlib import contextmanager
    class DummyPV:
        @staticmethod
        @contextmanager
        def step(name):
            class StepRecorder:
                def metric(self, *args, **kwargs): pass
                def artifact(self, *args, **kwargs): pass
            yield StepRecorder()
    pv = DummyPV()

from src.data_fetcher import prepare_data
from src.logic import MinimalistERGridBacktest, plot_equity_curve

def main():
    print("=" * 70)
    print("MINIMALIST ER SPOT GRID — IN-SAMPLE EVALUATION (2021-2023)")
    print("=" * 70)
    
    cfg_path = os.path.join(curr_dir, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
        
    strat_cfg = config.get("strategy", {})
    bundle = prepare_data(config, "in_sample")
    
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
        risk_free_rate=strat_cfg.get("risk_free_rate", 0.06)
    )
    
    res = sim.backtest(bundle)
    print(f"Total Return (HPR): {res['hpr']:+.2f}% ({res['net_profit']:+,.0f} VND)")
    print(f"Annual Return:      {res['annual_return']:+.2f}%")
    print(f"Max Drawdown:       {res['max_drawdown']:.2f}%")
    print(f"Daily Sharpe:       {res['daily_sharpe']:.3f} (30m Sharpe: {res['sharpe_ratio']:.3f})")
    print(f"Calmar Ratio:       {res['calmar_ratio']:.3f}")
    print(f"Spot Harvest PnL:   {res['spot_harvest_pnl']:+,.0f} VND (TP Trades: {res['tp_trades']})")
    print(f"Rotation PnL:       {res['rotation_pnl']:+,.0f} VND (Rotations: {res['rot_trades']})")
    print(f"Floor Stop PnL:     {res['floor_stop_pnl']:+,.0f} VND (Floor Stops: {res['stop_trades']})")
    print(f"Total Trades:       {res['total_trades']} (Win Rate: {res['win_rate']:.1f}%)")
    print(f"Period-End Inventory:{res['open_inventory_value']:+,.0f} VND (Unrealized: {res['unrealized_pnl']:+,.0f} VND)")
    print("=" * 70)

    with pv.step("in_sample") as r:
        r.metric("total_return", float(round(res["hpr"] / 100.0, 4)), unit="fraction")
        r.metric("annual_return", float(round(res["annual_return"] / 100.0, 4)), unit="fraction")
        r.metric("max_drawdown", float(round(abs(res["max_drawdown"]) / 100.0, 4)), unit="fraction")
        r.metric("sharpe_ratio", float(round(res["sharpe_ratio"], 3)), unit="ratio")
        r.metric("win_rate", float(round(res["win_rate"] / 100.0, 4)), unit="fraction")
        r.metric("total_trades", int(res["total_trades"]), unit="count")
        r.metric("tp_trades", int(res["tp_trades"]), unit="count")
        chart_path = "images/equity_curve_in_sample.png"
        plot_equity_curve(
            res["equity_series"],
            strat_cfg.get("capital", 1_000_000_000),
            "Minimalist ER Spot Grid — Equity Curve [IN SAMPLE]",
            os.path.join(curr_dir, chart_path)
        )
        if os.path.exists(os.path.join(curr_dir, chart_path)):
            r.artifact("equity_curve", chart_path, kind="chart")

if __name__ == "__main__":
    main()
