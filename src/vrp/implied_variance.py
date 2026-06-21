"""Model-free implied variance replication, per the CBOE VIX white paper methodology.

For each date: pick near-term/next-term expiries bracketing 30 days, compute
each term's model-free variance from the OTM strike strip (using the forward
derived from put-call parity, not the raw spot), then time-interpolate to a
constant 30-day tenor. Output is a synthetic "VIX" series to validate against
the real one — see RESULTS.md.

Known limitation: Q(K) uses last-trade daily close,
not bid/ask mid, because true quote data was unaffordable at this project's
data budget (see databento.py docstring). ΔK spacing and the tail-truncation
point are computed from the *full listed strike grid* (every strike ever
defined for that expiry, regardless of whether it traded that day) rather
than from the surviving traded strikes — using only traded strikes for ΔK
silently inflates the weight of whichever strike survives next to an
untraded gap, which is exactly what produced a 39-point blowup on
2020-03-16 during initial validation.
"""

import numpy as np
import pandas as pd

from config import TARGET_TENOR_DAYS

DAYS_PER_YEAR = 365.0


def _select_bracket_expiries(dtes: list[int], target_days: int = TARGET_TENOR_DAYS) -> tuple[int, int] | None:
    """Return (near_dte, next_dte) that genuinely straddle target_days, or None.

    Requires near_dte <= target_days <= next_dte. Without weeklies in our SPX
    chain (see databento.py — SPXW wasn't affordable at this budget), the
    nearest available monthly expiry sometimes already exceeds target_days
    when the monthly cycle drifts past it. Picking the two nearest expiries
    regardless of whether they bracket 30 days turns the time-interpolation
    formula into extrapolation, with weights outside [0, 1] that can amplify
    the gap between the two legs' variance without bound — this produced a
    >1500-point synthetic VIX on 2023-05-16 before this check was added.
    Dropping the date is the honest choice over fabricating a number.
    """
    unexpired = sorted(d for d in dtes if d > 0)
    if len(unexpired) < 2:
        return None

    near_candidates = [d for d in unexpired if d <= target_days]
    if not near_candidates:
        return None
    near = max(near_candidates)
    later = [d for d in unexpired if d >= target_days and d > near]
    if not later:
        return None
    nxt = min(later)
    return near, nxt


MIN_VOLUME_FOR_FORWARD = 10


def _forward_and_k0(
    calls: pd.Series,
    puts: pd.Series,
    call_vol: pd.Series,
    put_vol: pd.Series,
    full_grid: np.ndarray,
    r: float,
    T: float,
):
    """Forward price F via put-call parity at the strike minimizing |C - P|, and K0 just below F.

    full_grid: every strike ever listed for this expiry (not just strikes that
    traded today) — K0 must be a real listed strike.

    Restricts the |C - P| search to strikes where BOTH legs traded at least
    MIN_VOLUME_FOR_FORWARD contracts. A single 1-lot stale/bad print (e.g. a
    deep-ITM put printing near zero) can otherwise make |C - P| look smallest
    at a strike nowhere near the real forward, which then corrupts the whole
    day's call/put split downstream — this happened on 2020-03-16 with a
    single $0.08 print on a put that traded $700-900 every other day that
    month (see RESULTS.md). Falls back to the unfiltered set only if no
    strike clears the liquidity bar.
    """
    common = sorted(set(calls.index) & set(puts.index))
    if not common:
        return None

    liquid = [k for k in common if call_vol.get(k, 0) >= MIN_VOLUME_FOR_FORWARD and put_vol.get(k, 0) >= MIN_VOLUME_FOR_FORWARD]
    candidates = liquid if liquid else common

    diffs = {k: calls[k] - puts[k] for k in candidates}
    k_star = min(diffs, key=lambda k: abs(diffs[k]))
    forward = k_star + np.exp(r * T) * diffs[k_star]

    below = full_grid[full_grid <= forward]
    if len(below) == 0:
        return None
    k0 = below.max()
    return forward, k0


GRID_SPACING_CAP_MULTIPLIER = 3


def _weight_by_grid_spacing(full_grid: np.ndarray, used_strikes: list[float]) -> dict:
    """ΔK for each strike that actually has a usable quote today.

    Base case: gradient over the strikes that actually traded today (an
    irregular-grid trapezoidal rule sized to the available samples). This
    tracked the real VIX better, in aggregate, than purely using true
    listed-grid spacing (which under-weights regions where trading was simply
    thin that day, not absent). But an isolated illiquid strike next to a long
    gap of untraded strikes can blow ΔK up arbitrarily — so each strike's ΔK
    is capped at GRID_SPACING_CAP_MULTIPLIER times its *true* neighbor
    distance in the full listed grid, which bounds the damage from any single
    gap without distorting normal, densely-traded regions.
    """
    used = np.array(sorted(used_strikes))
    if len(used) < 2:
        return {}
    survivor_dk = np.gradient(used)

    n = len(full_grid)
    deltas = {}
    for k, survivor in zip(used, survivor_dk):
        idx = int(np.searchsorted(full_grid, k))
        lo = full_grid[idx - 1] if idx - 1 >= 0 else None
        hi = full_grid[idx + 1] if idx + 1 < n else None
        if lo is not None and hi is not None:
            local = (hi - lo) / 2
        elif hi is not None:
            local = hi - k
        elif lo is not None:
            local = k - lo
        else:
            local = survivor
        deltas[k] = min(survivor, GRID_SPACING_CAP_MULTIPLIER * local)
    return deltas


def term_variance(day_chain: pd.DataFrame, expiry_dte: int, r: float, full_grid: np.ndarray) -> float | None:
    """Model-free variance for a single expiry on a single date, per the VIX strip formula."""
    chain = day_chain[day_chain["dte"] == expiry_dte]
    calls = chain[chain["right"] == "C"].set_index("strike")["close"]
    puts = chain[chain["right"] == "P"].set_index("strike")["close"]
    call_vol = chain[chain["right"] == "C"].set_index("strike")["volume"]
    put_vol = chain[chain["right"] == "P"].set_index("strike")["volume"]
    if len(calls) + len(puts) < 3 or len(full_grid) < 3:
        return None

    T = expiry_dte / DAYS_PER_YEAR
    fwd_k0 = _forward_and_k0(calls, puts, call_vol, put_vol, full_grid, r, T)
    if fwd_k0 is None:
        return None
    forward, k0 = fwd_k0

    # Q(K): puts below K0, calls above K0, average of both at K0.
    q = {}
    for k in set(calls.index) | set(puts.index):
        has_c, has_p = k in calls.index, k in puts.index
        if k < k0 and has_p:
            q[k] = puts[k]
        elif k > k0 and has_c:
            q[k] = calls[k]
        elif k == k0 and has_c and has_p:
            q[k] = 0.5 * (calls[k] + puts[k])
    if len(q) < 3:
        return None

    deltas = _weight_by_grid_spacing(full_grid, sorted(q.keys()))
    if len(deltas) < 3:
        return None

    contributions = sum(
        dk / k**2 * np.exp(r * T) * q[k] for k, dk in deltas.items()
    )
    variance = (2 / T) * contributions - (1 / T) * (forward / k0 - 1) ** 2
    return variance


def synthetic_30day_variance_series(panel: pd.DataFrame, grid: pd.DataFrame, rate_series: pd.Series) -> pd.DataFrame:
    """panel: cleaned, traded-only option panel (date, expiry, dte, right, strike, close, volume).
    grid: full listed strike grid from cleaning.full_strike_grid (expiry, strike), independent
    of whether each strike traded that day.
    rate_series: daily risk-free rate (decimal, e.g. 0.02 for 2%), indexed by date,
    used as a single continuously-compounded proxy for both near/next legs —
    a documented simplification vs. VIX's two-point yield-curve interpolation.

    Returns a DataFrame indexed by date with columns: variance_30d, vol_30d_pct,
    near_dte, next_dte.
    """
    grids_by_expiry = {
        expiry: np.sort(group["strike"].unique()) for expiry, group in grid.groupby("expiry")
    }

    rows = []
    for date, day_chain in panel.groupby("date"):
        bracket = _select_bracket_expiries(day_chain["dte"].unique().tolist())
        if bracket is None:
            continue
        near_dte, next_dte = bracket

        r = rate_series.asof(date)
        if pd.isna(r):
            continue

        near_expiry = date + pd.Timedelta(days=near_dte)
        next_expiry = date + pd.Timedelta(days=next_dte)
        near_grid = grids_by_expiry.get(near_expiry)
        next_grid = grids_by_expiry.get(next_expiry)
        if near_grid is None or next_grid is None:
            continue

        var_near = term_variance(day_chain, near_dte, r, near_grid)
        var_next = term_variance(day_chain, next_dte, r, next_grid)
        if var_near is None or var_next is None:
            continue

        n1, n2, n30, n365 = near_dte, next_dte, TARGET_TENOR_DAYS, DAYS_PER_YEAR
        t1, t2 = n1 / n365, n2 / n365
        w_near = (n2 - n30) / (n2 - n1)
        w_next = (n30 - n1) / (n2 - n1)
        var_30 = (t1 * var_near * w_near + t2 * var_next * w_next) * (n365 / n30)

        if var_30 <= 0:
            continue

        rows.append(
            {
                "date": date,
                "variance_30d": var_30,
                "vol_30d_pct": 100 * np.sqrt(var_30),
                "near_dte": near_dte,
                "next_dte": next_dte,
            }
        )

    return pd.DataFrame(rows).set_index("date").sort_index()
