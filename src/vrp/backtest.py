"""Performance statistics for the short-variance carry strategy.

P&L is reported as a fraction of the fixed vega notional — the risk-capital
base the strategy is sized against. CAGR treats cumulative P&L-as-fraction
as if compounding into that base — a standard simplifying convention for
fixed-risk-budget overlay strategies, not literal reinvestment of
variance-swap payoffs.
"""

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def daily_returns(pnl_usd: pd.Series, vega_notional_usd: float) -> pd.Series:
    return pnl_usd / vega_notional_usd


def _nav_with_liquidation_floor(returns: pd.Series) -> pd.Series:
    """Compounding NAV, floored at zero once wiped out.

    A single day's loss can exceed 100% of the risk-capital base when
    unhedged short variance is sized aggressively (this happened during the
    COVID validation run) — real accounts get liquidated/margin-called at
    that point, not allowed to go negative and keep "compounding" through
    sign flips. Once NAV hits zero it stays at zero; this is itself a real
    finding (the strategy as sized did not survive), not a smoothing fix.
    """
    nav = (1 + returns).cumprod()
    wiped_out = nav[nav <= 0]
    if not wiped_out.empty:
        nav.loc[wiped_out.index.min():] = 0.0
    return nav


def performance_stats(returns: pd.Series, cvar_quantile: float = 0.05) -> dict:
    returns = returns.dropna()
    nav = _nav_with_liquidation_floor(returns)
    n_years = len(returns) / TRADING_DAYS_PER_YEAR

    running_max = nav.cummax()
    drawdown = nav / running_max - 1

    cvar_threshold = returns.quantile(cvar_quantile)
    cvar = returns[returns <= cvar_threshold].mean()

    ann_return = nav.iloc[-1] ** (1 / n_years) - 1 if n_years > 0 else np.nan
    ann_vol = returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR)

    return {
        "n_days": len(returns),
        "cagr": ann_return,
        "ann_vol": ann_vol,
        "sharpe": (returns.mean() * TRADING_DAYS_PER_YEAR) / ann_vol if ann_vol else np.nan,
        "max_drawdown": drawdown.min(),
        "worst_day": returns.min(),
        f"cvar_{int(cvar_quantile*100)}pct": cvar,
        "total_return": nav.iloc[-1] - 1,
    }


def regime_performance(returns: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame({"ret": returns})
    df["year"] = df.index.year

    def regime(y: int) -> str:
        if y == 2020:
            return "2020 (COVID)"
        if y == 2022:
            return "2022 (bear market)"
        return "calm/other"

    df["regime"] = df["year"].map(regime)
    rows = {}
    for name, g in df.groupby("regime"):
        stats = performance_stats(g["ret"])
        rows[name] = stats
    return pd.DataFrame(rows).T
