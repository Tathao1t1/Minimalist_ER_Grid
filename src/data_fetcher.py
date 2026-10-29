import os
import pandas as pd

def prepare_data(config, split="in_sample", include_warmup=True, warmup_days=40):
    """
    Load spot bar dataset and benchmark data for the requested split.
    Automatically prepends prior historical trading sessions as indicator warm-up
    so trading can begin cleanly on Day 1 of the evaluation period.
    """
    data_cfg = config.get("data", {})
    strat_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    split_map = {
        "out_of_sample": "out_sample",
        "forward_holdout": "holdout",
        "year_2025": "test_2025"
    }
    split_norm = split_map.get(split, split)
    file_key = f"{split_norm}_file"
    raw_path = data_cfg.get(file_key, "")
    if not raw_path:
        raise ValueError(f"No file path configured for split '{split}' (key '{file_key}')")
    if not os.path.isabs(raw_path):
        spot_path = os.path.join(strat_dir, raw_path)
    else:
        spot_path = raw_path
        
    if not os.path.exists(spot_path):
        # Fallback to workspace root data directory
        spot_path = os.path.join(strat_dir, "..", "..", raw_path)
        
    if not os.path.exists(spot_path):
        raise FileNotFoundError(f"Cannot find spot data file at {spot_path}")
        
    bars_df = pd.read_parquet(spot_path)
    if "bar_close" in bars_df.columns:
        bars_df["bar_close"] = pd.to_datetime(bars_df["bar_close"])
    elif "datetime" in bars_df.columns:
        bars_df["bar_close"] = pd.to_datetime(bars_df["datetime"])
    bars_df["is_warmup"] = False

    # Pre-split Indicator Warm-up
    if include_warmup and warmup_days > 0:
        prior_file_map = {
            "out_sample": "in_sample_file",
            "test_2025": "out_sample_file",
            "holdout": "test_2025_file"
        }
        prior_key = prior_file_map.get(split_norm)
        if prior_key and data_cfg.get(prior_key):
            prior_raw = data_cfg.get(prior_key)
            prior_path = prior_raw if os.path.isabs(prior_raw) else os.path.join(strat_dir, prior_raw)
            if not os.path.exists(prior_path):
                prior_path = os.path.join(strat_dir, "..", "..", prior_raw)
            if os.path.exists(prior_path):
                prior_df = pd.read_parquet(prior_path)
                if "bar_close" in prior_df.columns:
                    prior_df["bar_close"] = pd.to_datetime(prior_df["bar_close"])
                elif "datetime" in prior_df.columns:
                    prior_df["bar_close"] = pd.to_datetime(prior_df["datetime"])
                prior_dates = sorted(prior_df["bar_close"].dt.date.unique())
                warmup_target_dates = prior_dates[-warmup_days:]
                prior_warmup = prior_df[prior_df["bar_close"].dt.date.isin(warmup_target_dates)].copy()
                prior_warmup["is_warmup"] = True
                bars_df = pd.concat([prior_warmup, bars_df]).sort_values(["bar_close", "tickersymbol"]).reset_index(drop=True)
        
    date_info = data_cfg.get(split, {})
    start_date = date_info.get("start_date", "2021-01-01")
    end_date = date_info.get("end_date", "2026-10-01")
    
    # Load corporate action adjustment factors if available
    ca_raw = os.path.join(strat_dir, "data", "corporate_actions", "adjustment_factors.parquet")
    if not os.path.exists(ca_raw):
        ca_raw = os.path.join(strat_dir, "..", "..", "data", "corporate_actions", "adjustment_factors.parquet")
        
    if os.path.exists(ca_raw):
        ca_df = pd.read_parquet(ca_raw)
        ca_df["trade_date"] = pd.to_datetime(ca_df["trade_date"]).dt.date
        bars_df["trade_date"] = bars_df["bar_close"].dt.date
        bars_df = bars_df.merge(
            ca_df[["tickersymbol", "trade_date", "adj_factor"]],
            on=["tickersymbol", "trade_date"],
            how="left"
        )
        bars_df["adj_factor"] = bars_df["adj_factor"].fillna(1.0)
        for col in ["open", "high", "low", "close"]:
            if col in bars_df.columns:
                bars_df[col] = bars_df[col] * bars_df["adj_factor"]
    
    # Load benchmark daily if exists
    vn30d_raw = data_cfg.get("vn30_daily_file", "")
    vn30d_path = vn30d_raw if os.path.isabs(vn30d_raw) else os.path.join(strat_dir, vn30d_raw)
    if not os.path.exists(vn30d_path):
        vn30d_path = os.path.join(strat_dir, "..", "..", vn30d_raw)
        
    vn30_daily = pd.DataFrame()
    if os.path.exists(vn30d_path):
        vn30_daily = pd.read_parquet(vn30d_path)
        
    return {
        "bars": bars_df,
        "vn30d": vn30_daily,
        "start_date": start_date,
        "end_date": end_date
    }
