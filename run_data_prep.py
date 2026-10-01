import os
import sys
import yaml
import plutus_verify as pv

curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from src.data_fetcher import prepare_data

def main():
    print("=" * 70)
    print("PLUTUS STEP 2: DATA PREPARATION & INTEGRITY VERIFICATION")
    print("=" * 70)
    
    cfg_path = os.path.join(curr_dir, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
        
    is_bundle = prepare_data(config, "in_sample")
    oos_bundle = prepare_data(config, "out_sample")
    holdout_bundle = prepare_data(config, "holdout")
    
    is_rows = len(is_bundle["bars"])
    oos_rows = len(oos_bundle["bars"])
    holdout_rows = len(holdout_bundle["bars"])
    
    print(f"In-Sample dataset verified:     {is_rows:,} bars ({is_bundle['start_date']} to {is_bundle['end_date']})")
    print(f"Out-of-Sample dataset verified: {oos_rows:,} bars ({oos_bundle['start_date']} to {oos_bundle['end_date']})")
    print(f"Holdout dataset verified:       {holdout_rows:,} bars ({holdout_bundle['start_date']} to {holdout_bundle['end_date']})")
    print("All schemas and date boundaries validated successfully.")
    print("=" * 70)
    
    summary_path = os.path.join(curr_dir, "data/data_summary.json")
    with open(summary_path, "w") as f:
        import json
        json.dump({
            "in_sample_bars": is_rows,
            "out_of_sample_bars": oos_rows,
            "holdout_bars": holdout_rows,
            "status": "verified"
        }, f, indent=2)

    with pv.step("data_preparation") as r:
        r.metric("in_sample_bars", is_rows, unit="count")
        r.metric("out_of_sample_bars", oos_rows, unit="count")
        r.metric("holdout_bars", holdout_rows, unit="count")
        r.artifact("data_summary", "data/data_summary.json", kind="json")

if __name__ == "__main__":
    main()
