"""Transaction cost model for the short-variance carry strategy (Phase 5).

A single bps rate applied to the vega notional traded at entry: one
transaction-cost component plus the bid-ask half-spread paid on both sides
of establishing the position. Both rates are placeholders (see config.py)
pending real cost data — documented as an explicit assumption in RESULTS.md,
not smuggled in as a precise number.
"""

from config import BID_ASK_HALF_SPREAD_BPS, TRANSACTION_COST_BPS


def entry_cost_usd(
    vega_notional_usd: float,
    transaction_cost_bps: float = TRANSACTION_COST_BPS,
    bid_ask_half_spread_bps: float = BID_ASK_HALF_SPREAD_BPS,
) -> float:
    total_bps = transaction_cost_bps + 2 * bid_ask_half_spread_bps
    return abs(vega_notional_usd) * total_bps / 10_000.0
