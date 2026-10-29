import os
import sys
import yaml

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
curr_dir = repo_root

try:
    import plutus_verify as pv
except ImportError:
    print("[WARNING] plutus_verify module not found; running in standalone mode without recording to .plutus/run/")
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
    print("=" * 75)
    print("MINIMALIST ER SPOT GRID — OUT-OF-SAMPLE EVALUATION (2024)")
    print("=" * 75)
    
    cfg_path = os.path.join(curr_dir, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
        
    strat_cfg = config.get("strategy", {})
    best_params_path = os.path.join(curr_dir, "config/best_params.yaml")
    if os.path.exists(best_params_path):
        with open(best_params_path, "r") as f:
            best_cfg = yaml.safe_load(f)
        opt_strat = best_cfg.get("strategy", {})
        for k in ["selection_lookback", "selection_rebalance_days", "n_levels", "grid_spacing_pct"]:
            if k in opt_strat:
                strat_cfg[k] = opt_strat[k]
        print(f"Piping parameters from config/best_params.yaml: lookback={strat_cfg.get('selection_lookback')}d, rebalance={strat_cfg.get('selection_rebalance_days')}d, n_levels={strat_cfg['n_levels']}, grid_spacing_pct={strat_cfg['grid_spacing_pct']}")
    else:
        print(f"Using default parameters from config.yaml: lookback={strat_cfg.get('selection_lookback', 40)}d, rebalance={strat_cfg.get('selection_rebalance_days', 10)}d, n_levels={strat_cfg.get('n_levels', 18)}, grid_spacing_pct={strat_cfg.get('grid_spacing_pct', 0.018)}")
        
    bundle = prepare_data(config, "out_sample")
    
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
        grid_spacing_pct=strat_cfg.get("grid_spacing_pct", 0.028),
        stop_buffer_levels=strat_cfg.get("stop_buffer_levels", 2),
        trend_filter=strat_cfg.get("trend_filter", "none"),
        risk_free_rate=strat_cfg.get("risk_free_rate", 0.06)
    )
    
    res = sim.backtest(bundle)
    
    print("-" * 75)
    print("FINANCIAL PERFORMANCE & BENCHMARK COMPARISON")
    print("-" * 75)
    print(f"Holding Period Return (HPR): {res['hpr']:+.2f}% ({int(res['net_profit']):+,d} VND)")
    print(f"Annualized Return (CAGR):     {res['annual_return']:+.2f}%")
    print(f"Max Drawdown (MDD):           {res['max_drawdown']:.2f}% (Duration: {res['longest_dd_days']} days)")
    print(f"Daily Sharpe (Rf=6%):         {res['daily_sharpe']:.3f} (30m Sharpe: {res['sharpe_ratio']:.3f})")
    print(f"Calmar Ratio:                 {res['calmar_ratio']:.3f}")
    print(f"VN30 Benchmark HPR:           {res['benchmark_hpr']:+.2f}%")
    print(f"VN30 Benchmark MDD:           {res['benchmark_mdd']:.2f}%")
    print(f"Strategy Excess Return:       {res['excess_return']:+.2f}%")
    print(f"Market Beta:                  {res['beta']:.3f} (Ultra-low systematic exposure)")
    print(f"Annualized Jensen's Alpha:    {res['alpha']:+.2f}%")
    print(f"Average Capital Invested:     {res['avg_capital_invested_pct']:.1f}% ({100-res['avg_capital_invested_pct']:.1f}% Cash)")
    print("-" * 75)
    print("SPOT HARVEST & TRADE EXECUTION BREAKDOWN")
    print("-" * 75)
    print(f"Take-Profit Harvests:         {int(res['spot_harvest_pnl']):+,d} VND ({res['tp_trades']} trades)")
    print(f"Whitelist Rotation Exits:     {int(res['rotation_pnl']):+,d} VND ({res['rot_trades']} trades)")
    print(f"Floor Stop Liquidations:      {int(res['floor_stop_pnl']):+,d} VND ({res['stop_episodes']} episodes, {res['stop_trades']} lots)")
    print(f"Total Completed Trades:       {res['total_trades']} (Win Rate: {res['win_rate']:.1f}%)")
    print(f"Simulated Transaction Costs:  50 bps roundtrip (15 bps buy/sell fee, 10 bps tax, 5 bps slippage)")
    print("-" * 75)
    print("PERIOD-END OPEN INVENTORY BREAKDOWN")
    print("-" * 75)
    if res['open_positions']:
        pos_str = ", ".join(f"{k}: {v:,} shs" for k, v in sorted(res['open_positions'].items()))
        print(f"Open Positions:               {pos_str}")
    else:
        print(f"Open Positions:               None (All cash)")
    print(f"Cost Basis:                   {int(res['open_cost_basis']):+,d} VND")
    print(f"Mark-to-Market Valuation:     {int(res['open_inventory_value']):+,d} VND")
    print(f"Unrealized PnL:               {int(res['unrealized_pnl']):+,d} VND ({res['unrealized_pnl_pct']:+.2f}%)")
    print(f"Closing Cash Balance:         {int(res['cash_balance']):+,d} VND")
    print(f"Total Portfolio Value:        {int(res['final_capital']):+,d} VND")
    print("Note: Open inventory is marked to market at period-end close; no artificial forced liquidation.")
    print("=" * 75)

    with pv.step("out_of_sample") as r:
        r.metric("hpr", float(round(res["hpr"] / 100.0, 4)), unit="fraction")
        r.metric("annual_return", float(round(res["annual_return"] / 100.0, 4)), unit="fraction")
        r.metric("max_drawdown", float(round(abs(res["max_drawdown"]) / 100.0, 4)), unit="fraction")
        r.metric("daily_sharpe", float(round(res["daily_sharpe"], 3)), unit="ratio")
        r.metric("calmar_ratio", float(round(res["calmar_ratio"], 3)), unit="ratio")
        r.metric("benchmark_hpr", float(round(res["benchmark_hpr"] / 100.0, 4)), unit="fraction")
        r.metric("excess_return", float(round(res["excess_return"] / 100.0, 4)), unit="fraction")
        r.metric("beta", float(round(res["beta"], 3)), unit="ratio")
        r.metric("win_rate", float(round(res["win_rate"] / 100.0, 4)), unit="fraction")
        r.metric("total_trades", int(res["total_trades"]), unit="count")
        r.metric("tp_trades", int(res["tp_trades"]), unit="count")
        r.metric("stop_episodes", int(res["stop_episodes"]), unit="count")
        r.metric("open_inventory_value", float(round(res["open_inventory_value"], 0)), unit="ratio")
        r.metric("unrealized_pnl", float(round(res["unrealized_pnl"], 0)), unit="ratio")
        
        chart_path = "images/equity_curve_out_sample.png"
        plot_equity_curve(
            res["equity_series"],
            strat_cfg.get("capital", 1_000_000_000),
            "Minimalist ER Spot Grid — Equity vs VN30 Benchmark [OUT OF SAMPLE (2024)]",
            os.path.join(curr_dir, chart_path),
            bmk_series=res.get("benchmark_series")
        )
        if os.path.exists(os.path.join(curr_dir, chart_path)):
            r.artifact("equity_curve", chart_path, kind="chart")

if __name__ == "__main__":
    main()
