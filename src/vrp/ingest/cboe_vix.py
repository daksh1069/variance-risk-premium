"""Free CBOE VIX history — ground truth for validating the synthetic implied-vol series."""

import pandas as pd
import requests

from config import DATA_EXTERNAL_DIR

VIX_HISTORY_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
CACHE_PATH = DATA_EXTERNAL_DIR / "vix_history.csv"


def fetch_vix_history(force_refresh: bool = False) -> pd.DataFrame:
    """Return daily VIX close history as a DataFrame indexed by date.

    Caches the raw CSV under data/external so re-runs don't re-hit CBOE.
    """
    if force_refresh or not CACHE_PATH.exists():
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(VIX_HISTORY_URL, timeout=30)
        response.raise_for_status()
        CACHE_PATH.write_bytes(response.content)

    df = pd.read_csv(CACHE_PATH)
    df["DATE"] = pd.to_datetime(df["DATE"])
    df = df.rename(columns={"DATE": "date", "CLOSE": "vix_close"})
    df = df.set_index("date").sort_index()
    return df[["vix_close"]]
