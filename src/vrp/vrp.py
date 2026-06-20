"""Variance risk premium (Phase 4): today's implied variance minus the
variance subsequently realized over the next 30 days.

Strictly forward-looking by construction (matches realized_variance.py's
alignment) — implied_variance.loc[t] and realized_variance.loc[t] are never
mixed with information from before t on the realized side.
"""

import numpy as np
import pandas as pd


def compute_vrp(implied_variance: pd.Series, realized_variance: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"implied_variance": implied_variance, "realized_variance": realized_variance}).dropna()
    df["vrp"] = df["implied_variance"] - df["realized_variance"]
    df["implied_vol_pct"] = 100 * np.sqrt(df["implied_variance"])
    df["realized_vol_pct"] = 100 * np.sqrt(df["realized_variance"])
    df["vrp_vol_pts"] = df["implied_vol_pct"] - df["realized_vol_pct"]
    return df


def summary_stats(vrp_df: pd.DataFrame) -> dict:
    return {
        "n_days": len(vrp_df),
        "mean_vrp_vol_pts": vrp_df["vrp_vol_pts"].mean(),
        "median_vrp_vol_pts": vrp_df["vrp_vol_pts"].median(),
        "std_vrp_vol_pts": vrp_df["vrp_vol_pts"].std(),
        "pct_positive": (vrp_df["vrp"] > 0).mean() * 100,
        "mean_implied_vol_pct": vrp_df["implied_vol_pct"].mean(),
        "mean_realized_vol_pct": vrp_df["realized_vol_pct"].mean(),
    }


def regime_breakdown(vrp_df: pd.DataFrame) -> pd.DataFrame:
    df = vrp_df.copy()
    df["year"] = df.index.year

    def regime(y: int) -> str:
        if y == 2020:
            return "2020 (COVID)"
        if y == 2022:
            return "2022 (bear market)"
        return "calm/other"

    df["regime"] = df["year"].map(regime)
    return df.groupby("regime").apply(
        lambda g: pd.Series(
            {
                "mean_vrp_vol_pts": g["vrp_vol_pts"].mean(),
                "median_vrp_vol_pts": g["vrp_vol_pts"].median(),
                "pct_positive": (g["vrp"] > 0).mean() * 100,
                "n_days": len(g),
            }
        ),
        include_groups=False,
    )
