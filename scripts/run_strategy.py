"""Phase 5 driver: cost-aware short 30-day variance carry, gross vs. net.

Vega notional is normalized to $1 (a sizing base for the fixed-risk-budget
convention — see backtest.py docstring); costs and P&L scale linearly in it,
so the choice of dollar value doesn't affect any reported ratio.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config import DATA_RAW_DIR
from src.vrp import backtest, realized_variance as rv, strategy
from src.vrp.ingest import underlying

VEGA_NOTIONAL_USD = 1.0
TAIL_STOP_VOL_PCT = 35.0  # ~2.2 std above the full-sample mean trailing realized vol (14.3% mean, 9.2% std)

if __name__ == "__main__":
    vrp_df = pd.read_parquet(DATA_RAW_DIR.parent / "cache" / "vrp_2017_2023.parquet")
    spx = underlying.fetch_underlying_history()

    trailing_var = rv.trailing_realized_variance(spx, window_trading_days=10)
    trailing_vol_pct = 100 * trailing_var**0.5

    pnl = strategy.daily_pnl_series(
        vrp_df, trailing_vol_pct, spx.index, VEGA_NOTIONAL_USD, TAIL_STOP_VOL_PCT
    )
    out_path = DATA_RAW_DIR.parent / "cache" / "strategy_pnl_2017_2023.parquet"
    pnl.to_parquet(out_path)
    print(f"saved P&L series ({len(pnl)} rows) to {out_path}")
    print(f"entries skipped by tail stop: {(~pnl['entered'] & (pnl.index.isin(vrp_df.index))).sum()} of {len(vrp_df)} candidate days")

    gross_ret = backtest.daily_returns(pnl["gross_pnl_usd"], VEGA_NOTIONAL_USD)
    net_ret = backtest.daily_returns(pnl["net_pnl_usd"], VEGA_NOTIONAL_USD)

    print()
    print("=== GROSS ===")
    for k, v in backtest.performance_stats(gross_ret).items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    print()
    print("=== NET ===")
    for k, v in backtest.performance_stats(net_ret).items():
        print(f"  {k}: {v:.4f}" if isinstance(v, float) else f"  {k}: {v}")

    print()
    print("=== Regime breakdown (net) ===")
    print(backtest.regime_performance(net_ret))

    print()
    print("Worst 10 net days:")
    print(net_ret.sort_values().head(10))
