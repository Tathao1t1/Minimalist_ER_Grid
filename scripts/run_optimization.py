import os
import sys
import yaml
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

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
curr_dir = repo_root

from src.optimizer import run_optimization

def main():
    print("=" * 70)
    print("PLUTUS STEP 5: HYPERPARAMETER OPTIMIZATION (IN-SAMPLE EXHAUSTIVE GRID)")
    print("=" * 70)
    
    cfg_path = os.path.join(curr_dir, "config/config.yaml")
    with open(cfg_path, "r") as f:
        config = yaml.safe_load(f)
        
    best_params = run_optimization(config)
    
    with pv.step("optimization") as r:
        r.metric("best_n_levels", int(best_params["n_levels"]), unit="count")
        r.metric("best_grid_spacing_pct", float(best_params["grid_spacing_pct"]), unit="fraction")
        if os.path.exists(os.path.join(curr_dir, "results/optimization_grid_surface.csv")):
            r.artifact("grid_surface", "results/optimization_grid_surface.csv", kind="csv")
        if os.path.exists(os.path.join(curr_dir, "config/best_params.yaml")):
            r.artifact("best_params", "config/best_params.yaml", kind="other")

if __name__ == "__main__":
    main()
