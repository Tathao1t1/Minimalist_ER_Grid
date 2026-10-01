import os
import optuna
import yaml
from .logic import MinimalistERGridBacktest
from .data_fetcher import prepare_data

def run_optimization(config):
    """
    Run Optuna Bayesian hyperparameter optimization over grid parameters.
    """
    data_bundle = prepare_data(config, "in_sample")
    opt_cfg = config.get("optimization", {})
    strat_cfg = config.get("strategy", {})
    
    n_trials = opt_cfg.get("n_trials", 30)
    metric_target = opt_cfg.get("metric", "sharpe_ratio")
    
    n_levels_range = opt_cfg.get("n_levels_range", [14, 22])
    spacing_range = opt_cfg.get("grid_spacing_pct_range", [0.014, 0.022])
    
    def objective(trial):
        n_levels = trial.suggest_int("n_levels", n_levels_range[0], n_levels_range[1], step=2)
        grid_spacing_pct = trial.suggest_float("grid_spacing_pct", spacing_range[0], spacing_range[1], step=0.002)
        
        sim = MinimalistERGridBacktest(
            capital=strat_cfg.get("capital", 1_000_000_000),
            initial_spot_capital=strat_cfg.get("initial_spot_capital", 1_000_000_000),
            broker_fee=strat_cfg.get("broker_fee", 0.0015),
            sell_tax=strat_cfg.get("sell_tax", 0.0010),
            slippage=strat_cfg.get("slippage", 0.0005),
            selection_lookback=strat_cfg.get("selection_lookback", 40),
            selection_rebalance_days=strat_cfg.get("selection_rebalance_days", 10),
            top_k=strat_cfg.get("top_k", 4),
            n_levels=n_levels,
            grid_spacing_pct=grid_spacing_pct,
            stop_buffer_levels=strat_cfg.get("stop_buffer_levels", 2),
            trend_filter=strat_cfg.get("trend_filter", "none")
        )
        res = sim.backtest(data_bundle)
        return res.get(metric_target, -999.0)

    optuna.logging.set_verbosity(optuna.logging.WARNING)
    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials)
    
    print("\n" + "=" * 60)
    print("BAYESIAN OPTIMIZATION RESULTS:")
    print("=" * 60)
    print(f"Best Trial: {study.best_trial.number}")
    print(f"Best {metric_target}: {study.best_value:.4f}")
    print("Best Parameters:")
    for k, v in study.best_params.items():
        print(f"  • {k}: {v}")
    print("=" * 60)
    
    return study.best_params
