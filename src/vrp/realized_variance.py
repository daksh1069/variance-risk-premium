"""Realized variance from the SPX underlying (Phase 3).

Primary estimator: forward 30-calendar-day close-to-close realized variance,
aligned so realized_variance.loc[t] is the variance realized strictly over
(t, t+30 calendar days] — this is what Phase 4 (VRP) compares against
*today's* (t) implied variance. No look-ahead in the other direction: this
series is intentionally forward-looking by construction (that's the point
of VRP), but each value only uses returns that occur after t, never before.

Parkinson and Garman-Klass (from daily OHLC) are provided as robustness
checks per the brief — close-to-close is the headline estimator.
"""

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252
LN2 = np.log(2)


def daily_variance_close_to_close(ohlc: pd.DataFrame) -> pd.Series:
    """Squared log return per day — the close-to-close daily variance contribution."""
    log_ret = np.log(ohlc["close"] / ohlc["close"].shift(1))
    return (log_ret**2).dropna()


def daily_variance_parkinson(ohlc: pd.DataFrame) -> pd.Series:
    """High-low range estimator; more efficient than close-to-close, ignores drift."""
    return (1.0 / (4.0 * LN2)) * np.log(ohlc["high"] / ohlc["low"]) ** 2


def daily_variance_garman_klass(ohlc: pd.DataFrame) -> pd.Series:
    """Uses open/high/low/close; more efficient still, sensitive to overnight gaps."""
    hl = np.log(ohlc["high"] / ohlc["low"]) ** 2
    co = np.log(ohlc["close"] / ohlc["open"]) ** 2
    return 0.5 * hl - (2 * LN2 - 1) * co


def forward_realized_variance(daily_variance: pd.Series, window_calendar_days: int = 30) -> pd.Series:
    """Annualize the forward sum of a daily-variance series over (t, t+window] for each t.

    n (the actual number of trading days in that calendar window) varies with
    weekends/holidays, so each date is annualized by its own realized n, not
    a fixed assumed trading-day count.
    """
    dates = daily_variance.index
    result = {}
    for t in dates:
        window_end = t + pd.Timedelta(days=window_calendar_days)
        mask = (dates > t) & (dates <= window_end)
        n = int(mask.sum())
        if n == 0:
            continue
        result[t] = (TRADING_DAYS_PER_YEAR / n) * daily_variance[mask].sum()
    return pd.Series(result, dtype=float).sort_index()


def realized_variance_series(ohlc: pd.DataFrame, window_calendar_days: int = 30, estimator: str = "close_to_close") -> pd.Series:
    """estimator: 'close_to_close' (default/headline), 'parkinson', or 'garman_klass'."""
    daily_fns = {
        "close_to_close": daily_variance_close_to_close,
        "parkinson": daily_variance_parkinson,
        "garman_klass": daily_variance_garman_klass,
    }
    if estimator not in daily_fns:
        raise ValueError(f"Unknown estimator '{estimator}', expected one of {list(daily_fns)}")
    daily_var = daily_fns[estimator](ohlc)
    return forward_realized_variance(daily_var, window_calendar_days)
