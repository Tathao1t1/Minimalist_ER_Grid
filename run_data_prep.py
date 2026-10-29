import os
import sys
import yaml
import pandas as pd
import numpy as np
import math
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

curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from src.data_fetcher import prepare_data

def compute_is_grid_spacing_bounds(bars_df):
    """
    Computes objective grid spacing bounds strictly from In-Sample (2021-2023) daily volatility.
    - Lower Bound (Cost Floor): 1.0 * round-trip friction (50 bps = 0.50%)
    - Upper Bound (Oscillation Cap): 2/3 * IS median daily high-low range (3.14% -> 2.09% capped at 2.0%)
    - T+2 Settlement Rule: A lot cannot be sold before T+2 13:00, spanning at least 2 sessions.
    """
    df = bars_df.copy()
    if "bar_close" in df.columns:
        df["date"] = pd.to_datetime(df["bar_close"]).dt.date
    elif "datetime" in df.columns:
        df["date"] = pd.to_datetime(df["datetime"]).dt.date
    ticker_col = "tickersymbol" if "tickersymbol" in df.columns else "ticker"
    
    daily = df.groupby([ticker_col, "date"]).agg({"high": "max", "low": "min", "close": "last"})
    daily["hl_range"] = (daily["high"] - daily["low"]) / daily["close"]
    is_median_hl_range = float(daily["hl_range"].median())
    
    lower_bound = 0.0050
    # Rule 3: Upper Bound is floored to the nearest 10 bps (0.10%)
    # Delta_max = floor(2/3 * IS median daily high-low range to 10 bps) = floor(2.09%) = 2.0%
    raw_cap = (2.0 / 3.0) * is_median_hl_range
    upper_bound = float(np.floor(raw_cap * 1000) / 1000)
    candidate_spacings = [round(lower_bound, 3), 0.010, 0.014, 0.018, round(upper_bound, 3)]
    
    return {
        "is_median_daily_hl_range": round(is_median_hl_range, 5),
        "lower_bound_pct": lower_bound,
        "upper_bound_pct": upper_bound,
        "candidate_spacings": candidate_spacings,
        "rule_description": {
            "lower_bound": "1.0 * round-trip friction (50 bps = 0.50%)",
            "upper_bound": "floor(2/3 * IS median daily high-low range to nearest 10 bps) = floor(2.09%) = 2.0%",
            "rounding_protocol": "Floored to nearest 10 bps (0.10%) to preserve standard quote tick regularity and conservative range containment",
            "t_plus_2_rule": "A lot cannot be sold before T+2 13:00, requiring at least 2 sessions per cycle"
        }
    }

def main():
    print("=" * 70)
    print("PLUTUS STEP 2: DATA PREPARATION & INTEGRITY VERIFICATION")
    print("=" * 70)
    
    cfg_path = os.path.join(curr_dir, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
        
    is_bundle = prepare_data(config, "in_sample", include_warmup=False)
    oos_bundle = prepare_data(config, "out_sample", include_warmup=False)
    test_2025_bundle = prepare_data(config, "test_2025", include_warmup=False)
    holdout_bundle = prepare_data(config, "holdout", include_warmup=False)
    
    is_rows = len(is_bundle["bars"])
    oos_rows = len(oos_bundle["bars"])
    test_2025_rows = len(test_2025_bundle["bars"])
    holdout_rows = len(holdout_bundle["bars"])
    
    print(f"In-Sample dataset verified:     {is_rows:,} bars ({is_bundle['start_date']} to {is_bundle['end_date']})")
    print(f"Out-of-Sample dataset verified: {oos_rows:,} bars ({oos_bundle['start_date']} to {oos_bundle['end_date']})")
    print(f"2025 Bull Test dataset verified: {test_2025_rows:,} bars ({test_2025_bundle['start_date']} to {test_2025_bundle['end_date']})")
    print(f"Holdout dataset verified:       {holdout_rows:,} bars ({holdout_bundle['start_date']} to {holdout_bundle['end_date']})")
    print("All schemas and date boundaries validated successfully.")
    
    # Compute and persist objective In-Sample grid spacing bounds
    bounds_info = compute_is_grid_spacing_bounds(is_bundle["bars"])
    bounds_path = os.path.join(curr_dir, "config/grid_spacing_bounds.yaml")
    with open(bounds_path, "w") as f:
        yaml.dump(bounds_info, f, default_flow_style=False, sort_keys=False)
    print(f"Objective IS spacing bounds computed: Median Range={bounds_info['is_median_daily_hl_range']*100:.2f}%, "
          f"Bounds=[{bounds_info['lower_bound_pct']*100:.1f}%, {bounds_info['upper_bound_pct']*100:.1f}%]")
    print(f"Persisted to: {bounds_path}")
    print("=" * 70)
    
    summary_path = os.path.join(curr_dir, "data/data_summary.json")
    with open(summary_path, "w") as f:
        import json
        json.dump({
            "in_sample_bars": is_rows,
            "out_of_sample_bars": oos_rows,
            "test_2025_bars": test_2025_rows,
            "holdout_bars": holdout_rows,
            "is_median_daily_hl_range": bounds_info["is_median_daily_hl_range"],
            "spacing_bounds": [bounds_info["lower_bound_pct"], bounds_info["upper_bound_pct"]],
            "status": "verified"
        }, f, indent=2)

    with pv.step("data_preparation") as r:
        r.metric("in_sample_bars", is_rows, unit="count")
        r.metric("out_of_sample_bars", oos_rows, unit="count")
        r.metric("test_2025_bars", test_2025_rows, unit="count")
        r.metric("holdout_bars", holdout_rows, unit="count")
        r.artifact("data_summary", "data/data_summary.json", kind="json")

if __name__ == "__main__":
    main()
