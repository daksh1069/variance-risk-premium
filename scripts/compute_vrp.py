"""Phase 3 + 4 driver: realized variance from SPX returns, then the variance
risk premium against the Phase 2 synthetic implied-variance series.

Requires data/cache/synthetic_vs_vix_2017_2023.parquet (from
validate_full_history.py) to already exist.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import DATA_RAW_DIR
from src.vrp import realized_variance as rv
from src.vrp import vrp as vrp_mod
from src.vrp.ingest import underlying

IMPLIED_PATH = DATA_RAW_DIR.parent / "cache" / "synthetic_vs_vix_2017_2023.parquet"
OUT_PATH = DATA_RAW_DIR.parent / "cache" / "vrp_2017_2023.parquet"

ESTIMATORS = ["close_to_close", "parkinson", "garman_klass"]

if __name__ == "__main__":
    implied = pd.read_parquet(IMPLIED_PATH)["variance_30d"]
    spx = underlying.fetch_underlying_history()

    for estimator in ESTIMATORS:
        realized = rv.realized_variance_series(spx, window_calendar_days=30, estimator=estimator)
        df = vrp_mod.compute_vrp(implied, realized)
        out_path = DATA_RAW_DIR.parent / "cache" / f"vrp_2017_2023_{estimator}.parquet"
        df.to_parquet(out_path)
        print(f"[{estimator}] saved VRP series ({len(df)} rows) to {out_path}")
        if estimator == "close_to_close":
            df.to_parquet(OUT_PATH)  # headline estimator, kept at the original path too

    # trailing (backward-looking) realized vol for the dashboard's tail-stop display
    trailing = rv.trailing_realized_variance(spx, window_trading_days=10)
    trailing.to_frame("trailing_realized_variance").to_parquet(
        DATA_RAW_DIR.parent / "cache" / "trailing_realized_variance.parquet"
    )

    df = pd.read_parquet(OUT_PATH)
    print()
    print("Summary stats (close_to_close):")
    for k, v in vrp_mod.summary_stats(df).items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    print()
    print("Regime breakdown:")
    print(vrp_mod.regime_breakdown(df))

    print()
    print("Worst 10 VRP days:")
    print(df.sort_values("vrp_vol_pts").head(10)[["implied_vol_pct", "realized_vol_pct", "vrp_vol_pts"]])
