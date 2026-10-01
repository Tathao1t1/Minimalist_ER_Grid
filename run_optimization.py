import os
import sys
import yaml
import plutus_verify as pv

curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from src.optimizer import run_optimization

def main():
    print("=" * 70)
    print("PLUTUS STEP 5: HYPERPARAMETER OPTIMIZATION (IN-SAMPLE BAYESIAN)")
    print("=" * 70)
    
    cfg_path = os.path.join(curr_dir, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
        
    best_params = run_optimization(config)
    
    with pv.step("optimization") as r:
        r.metric("best_n_levels", int(best_params["n_levels"]), unit="count")
        r.metric("best_grid_spacing_pct", float(best_params["grid_spacing_pct"]), unit="fraction")

if __name__ == "__main__":
    main()
