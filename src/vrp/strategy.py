"""Phase 5: cost-aware short 30-day variance carry.

Each trading day with a valid VRP observation, short a 30-day variance swap
sized to a fixed vega notional. A variance swap's short-side terminal payoff
is `variance_notional * (strike_variance - realized_variance)`, i.e. exactly
`variance_notional * VRP(t)` given strike_variance ≈ implied_variance(t) —
this reuses the project's already-validated implied/realized machinery
rather than simulating a separate delta-hedged options book.

Positions overlap (a new 30-day tranche opens every trading day, so ~21 are
open at once). Each tranche's total payoff is amortized evenly across the
actual trading days it's held, for a smooth daily-resolution P&L series.

Risk control: a tail stop pauses *new* issuance when trailing (backward-
looking, no look-ahead) realized vol is already extreme — already-open
tranches still accrue and mature normally, since unwinding them would
require information not available at the time.
"""

import pandas as pd

from src.vrp.costs import entry_cost_usd


def daily_pnl_series(
    vrp_df: pd.DataFrame,
    trailing_realized_vol_pct: pd.Series,
    trading_calendar: pd.DatetimeIndex,
    vega_notional_usd: float,
    tail_stop_vol_pct: float,
    window_calendar_days: int = 30,
) -> pd.DataFrame:
    """Returns a DataFrame indexed by trading day with columns:
    gross_pnl_usd, cost_usd, net_pnl_usd, notional_usd (issued that day), entered (bool).
    """
    gross_pnl: dict[pd.Timestamp, float] = {}
    cost: dict[pd.Timestamp, float] = {}
    notional_issued: dict[pd.Timestamp, float] = {}
    entered: dict[pd.Timestamp, bool] = {}

    for t, row in vrp_df.iterrows():
        trailing_vol = trailing_realized_vol_pct.get(t)
        skip = pd.isna(trailing_vol) or trailing_vol > tail_stop_vol_pct

        notional_issued[t] = 0.0
        entered[t] = False
        cost[t] = 0.0

        if skip:
            continue

        window_end = t + pd.Timedelta(days=window_calendar_days)
        held_days = trading_calendar[(trading_calendar > t) & (trading_calendar <= window_end)]
        n = len(held_days)
        if n == 0:
            continue

        # ~n tranches are open at once (one entered per trading day, each held
        # for n days), so each new entry gets a 1/n share of the target vega
        # notional — otherwise aggregate outstanding exposure would be ~n
        # times the stated target, not equal to it.
        implied_vol_decimal = row["implied_vol_pct"] / 100.0
        per_entry_vega_usd = vega_notional_usd / n
        variance_notional = per_entry_vega_usd / (2 * implied_vol_decimal)
        total_payoff = variance_notional * row["vrp"]  # short side: implied - realized
        daily_accrual = total_payoff / n

        for d in held_days:
            gross_pnl[d] = gross_pnl.get(d, 0.0) + daily_accrual

        notional_issued[t] = per_entry_vega_usd
        entered[t] = True
        cost[t] = entry_cost_usd(per_entry_vega_usd)

    all_days = sorted(set(gross_pnl) | set(cost))
    out = pd.DataFrame(index=pd.DatetimeIndex(all_days))
    out["gross_pnl_usd"] = pd.Series(gross_pnl)
    out["cost_usd"] = pd.Series(cost)
    out["notional_usd"] = pd.Series(notional_issued)
    out["entered"] = pd.Series(entered)
    out = out.fillna({"gross_pnl_usd": 0.0, "cost_usd": 0.0, "notional_usd": 0.0, "entered": False})
    out["net_pnl_usd"] = out["gross_pnl_usd"] - out["cost_usd"]
    return out.sort_index()
