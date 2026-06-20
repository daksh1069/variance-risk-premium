"""Black-76 implied volatility for the dashboard's per-date smile/term-structure view.

Uses the same forward (F) derived from put-call parity that the replication
itself uses (implied_variance._forward_and_k0), not the raw spot — consistent
with the model-free framework used throughout this project. This is a
display-only convenience (the headline implied-variance numbers never use
per-strike Black-Scholes vol; see implied_variance.py) so a user can see what
a CBOE-VIX-equivalent smile actually looks like on a given day.
"""

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

from src.vrp.implied_variance import _forward_and_k0


def black76_price(forward: float, strike: float, rate: float, T: float, sigma: float, right: str) -> float:
    if sigma <= 0 or T <= 0:
        intrinsic = max(0.0, forward - strike) if right == "C" else max(0.0, strike - forward)
        return intrinsic * np.exp(-rate * T)
    d1 = (np.log(forward / strike) + 0.5 * sigma**2 * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    df = np.exp(-rate * T)
    if right == "C":
        return df * (forward * norm.cdf(d1) - strike * norm.cdf(d2))
    return df * (strike * norm.cdf(-d2) - forward * norm.cdf(-d1))


def implied_vol(price: float, forward: float, strike: float, rate: float, T: float, right: str) -> float:
    intrinsic = (max(0.0, forward - strike) if right == "C" else max(0.0, strike - forward)) * np.exp(-rate * T)
    if price <= intrinsic or T <= 0:
        return np.nan
    try:
        return brentq(lambda s: black76_price(forward, strike, rate, T, s, right) - price, 1e-4, 5.0)
    except ValueError:
        return np.nan


def smile_for_expiry(day_chain: pd.DataFrame, expiry_dte: int, r: float, full_grid: np.ndarray) -> pd.DataFrame:
    """One row per strike/right traded that day for this expiry, with its Black-76 implied vol."""
    chain = day_chain[day_chain["dte"] == expiry_dte]
    calls = chain[chain["right"] == "C"].set_index("strike")["close"]
    puts = chain[chain["right"] == "P"].set_index("strike")["close"]
    call_vol = chain[chain["right"] == "C"].set_index("strike")["volume"]
    put_vol = chain[chain["right"] == "P"].set_index("strike")["volume"]

    if len(calls) + len(puts) < 3 or len(full_grid) < 3:
        return pd.DataFrame(columns=["strike", "right", "iv", "moneyness"])

    T = expiry_dte / 365.0
    fwd_k0 = _forward_and_k0(calls, puts, call_vol, put_vol, full_grid, r, T)
    if fwd_k0 is None:
        return pd.DataFrame(columns=["strike", "right", "iv", "moneyness"])
    forward, _ = fwd_k0

    rows = []
    for strike, price in calls.items():
        iv = implied_vol(price, forward, strike, r, T, "C")
        if not np.isnan(iv):
            rows.append({"strike": strike, "right": "C", "iv": iv, "moneyness": strike / forward})
    for strike, price in puts.items():
        iv = implied_vol(price, forward, strike, r, T, "P")
        if not np.isnan(iv):
            rows.append({"strike": strike, "right": "P", "iv": iv, "moneyness": strike / forward})

    return pd.DataFrame(rows).sort_values("strike")
