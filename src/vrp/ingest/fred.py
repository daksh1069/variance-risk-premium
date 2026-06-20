"""Free FRED risk-free rate series, via the public fredgraph.csv endpoint (no API key needed)."""

import pandas as pd
import requests

from config import DATA_EXTERNAL_DIR

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
DEFAULT_SERIES_ID = "DGS3MO"  # 3-month constant maturity Treasury yield


def fetch_fred_series(series_id: str = DEFAULT_SERIES_ID, force_refresh: bool = False) -> pd.DataFrame:
    """Return a daily FRED series as a DataFrame indexed by date, cached locally."""
    cache_path = DATA_EXTERNAL_DIR / f"fred_{series_id}.csv"

    if force_refresh or not cache_path.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(FRED_CSV_URL.format(series_id=series_id), timeout=30)
        response.raise_for_status()
        cache_path.write_bytes(response.content)

    df = pd.read_csv(cache_path)
    df.columns = ["date", series_id]
    df["date"] = pd.to_datetime(df["date"])
    df[series_id] = pd.to_numeric(df[series_id], errors="coerce")
    df = df.set_index("date").sort_index()
    return df
