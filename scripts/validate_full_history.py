"""Build the synthetic 30-day implied-vol series across the full cached
2017-2023 SPX option history and validate it against the real VIX.

Excludes the original pilot files (2019-06, 2020-03) since those date
ranges are already covered by the 2019-Q2 / 2020-Q1 quarterly chunks —
including both would double-count those months.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import DATA_RAW_DIR
from src.vrp import cleaning, implied_variance
from src.vrp.ingest import cboe_vix, fred

LABELS = ["2017", "2018"] + [f"{y}-Q{q}" for y in range(2019, 2024) for q in range(1, 5)]


def load_full_history():
    raw_dir = DATA_RAW_DIR / "databento"
    panels, grids = [], []
    for label in LABELS:
        defn_path = raw_dir / f"definition_{label}.parquet"
        ohlcv_path = raw_dir / f"ohlcv-1d_{label}.parquet"
        panels.append(cleaning.load_panel(defn_path, ohlcv_path))
        grids.append(cleaning.full_strike_grid(defn_path))

    panel = pd.concat(panels, ignore_index=True)
    panel = cleaning.apply_quality_filters(panel)
    grid = pd.concat(grids, ignore_index=True).drop_duplicates()
    return panel, grid


if __name__ == "__main__":
    print("Loading and cleaning full 2017-2023 panel...")
    panel, grid = load_full_history()
    print(f"panel rows: {len(panel):,}  unique dates: {panel['date'].nunique():,}  unique expiries: {grid['expiry'].nunique():,}")

    rate = fred.fetch_fred_series()["DGS3MO"] / 100.0
    rate = rate.reindex(pd.date_range(rate.index.min(), rate.index.max())).ffill()

    print("Computing synthetic 30-day implied variance series...")
    synth = implied_variance.synthetic_30day_variance_series(panel, grid, rate)
    print(f"synthetic series rows: {len(synth):,}")

    vix = cboe_vix.fetch_vix_history()
    cmp = synth.join(vix, how="inner")
    cmp["error"] = cmp["vol_30d_pct"] - cmp["vix_close"]

    out_path = DATA_RAW_DIR.parent / "cache" / "synthetic_vs_vix_2017_2023.parquet"
    cmp.to_parquet(out_path)
    print(f"saved comparison to {out_path}")

    print()
    print(f"days compared: {len(cmp):,}")
    print(f"mean abs error: {cmp['error'].abs().mean():.3f} vol pts")
    print(f"median abs error: {cmp['error'].abs().median():.3f} vol pts")
    print(f"RMSE: {(cmp['error']**2).mean()**0.5:.3f} vol pts")
    print(f"95th pct abs error: {cmp['error'].abs().quantile(0.95):.3f} vol pts")
    print(f"max abs error: {cmp['error'].abs().max():.3f} vol pts on {cmp['error'].abs().idxmax().date()}")
    print(f"corr(synthetic, VIX): {cmp['vol_30d_pct'].corr(cmp['vix_close']):.4f}")

    print()
    print("Worst 10 days by abs error:")
    print(cmp.reindex(cmp["error"].abs().sort_values(ascending=False).index[:10])[["vol_30d_pct", "vix_close", "error", "near_dte", "next_dte"]])

    print()
    print("Per-year mean abs error:")
    cmp["year"] = cmp.index.year
    print(cmp.groupby("year")["error"].apply(lambda e: e.abs().mean()))
