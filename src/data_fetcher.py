import os
import pandas as pd

def prepare_data(config, split="in_sample"):
    """
    Load spot bar dataset and benchmark data for the requested split.
    """
    data_cfg = config.get("data", {})
    strat_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    file_key = f"{split}_file"
    raw_path = data_cfg.get(file_key, "")
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
        
    date_info = data_cfg.get(split, {})
    start_date = date_info.get("start_date", "2021-01-01")
    end_date = date_info.get("end_date", "2026-10-01")
    
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
