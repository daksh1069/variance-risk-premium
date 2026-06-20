"""Shared mapping from a date to its cached Databento chunk label.

Single source of truth for how scripts/fetch_databento.py and
scripts/validate_full_history.py named the cached chunks, so the dashboard's
on-demand snapshot loader (load just the one relevant chunk, not all 373MB)
doesn't duplicate or drift from that logic.
"""

from pathlib import Path

import pandas as pd

from config import DATA_RAW_DIR
from src.vrp import cleaning

ALL_LABELS = ["2017", "2018"] + [f"{y}-Q{q}" for y in range(2019, 2024) for q in range(1, 5)]


def chunk_label_for_date(date: pd.Timestamp) -> str | None:
    year = date.year
    if year in (2017, 2018):
        return str(year)
    if 2019 <= year <= 2023:
        quarter = (date.month - 1) // 3 + 1
        return f"{year}-Q{quarter}"
    return None


def load_chain_for_date(date: pd.Timestamp) -> pd.DataFrame:
    """Cleaned, quality-filtered option panel for every expiry traded on `date`."""
    label = chunk_label_for_date(date)
    if label is None:
        return pd.DataFrame(columns=["date", "expiry", "dte", "right", "strike", "close", "volume"])

    raw_dir = Path(DATA_RAW_DIR) / "databento"
    defn_path, ohlcv_path = raw_dir / f"definition_{label}.parquet", raw_dir / f"ohlcv-1d_{label}.parquet"
    if not defn_path.exists() or not ohlcv_path.exists():
        return pd.DataFrame(columns=["date", "expiry", "dte", "right", "strike", "close", "volume"])

    panel = cleaning.load_panel(defn_path, ohlcv_path)
    panel = cleaning.apply_quality_filters(panel)
    return panel[panel["date"] == pd.Timestamp(date).normalize()]


def full_strike_grid_for_date(date: pd.Timestamp) -> pd.DataFrame:
    label = chunk_label_for_date(date)
    if label is None:
        return pd.DataFrame(columns=["expiry", "strike"])
    defn_path = Path(DATA_RAW_DIR) / "databento" / f"definition_{label}.parquet"
    if not defn_path.exists():
        return pd.DataFrame(columns=["expiry", "strike"])
    return cleaning.full_strike_grid(defn_path)
