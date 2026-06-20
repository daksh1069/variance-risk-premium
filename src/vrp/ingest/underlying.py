"""SPX / SPY daily underlying prices via yfinance — used for realized variance and moneyness."""

import pandas as pd
import yfinance as yf

from config import DATA_EXTERNAL_DIR, START_DATE, UNDERLYING_TICKER


def fetch_underlying_history(
    ticker: str = UNDERLYING_TICKER,
    start: str = START_DATE,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Return daily OHLC close history for a ticker, cached locally as parquet."""
    cache_path = DATA_EXTERNAL_DIR / f"underlying_{ticker.strip('^')}.parquet"

    if force_refresh or not cache_path.exists():
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        df = yf.download(ticker, start=start, auto_adjust=False, progress=False)
        if df.empty:
            raise RuntimeError(f"yfinance returned no data for {ticker}")
        df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
        df.index.name = "date"
        df.to_parquet(cache_path)

    return pd.read_parquet(cache_path)
