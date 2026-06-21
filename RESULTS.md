# Results

Every number below is reproducible from the scripts cited next to it —
nothing here is hand-typed or rounded up from a different run.

**Status:** Complete. Run the dashboard: `streamlit run app.py`.

## Dashboard

`streamlit run app.py`. Sidebar controls split into two tiers: cost bps,
position sizing/tail-stop, realized-vol estimator, and gross/net recompute
live (they only touch the ~1,700-row VRP/strategy series — cheap). Target
tenor is shown but fixed at 30 days, since changing it would mean
re-running the full historical option-chain replication — the control is
disabled rather than silently faked. The Snapshot tab loads only the one
cached chunk file relevant to the selected date (not all 373MB of raw
option data) and shows a Black-76 implied-vol smile per expiry, built from
the same put-call-parity forward the replication itself uses.

## Assumptions

| Assumption | Value | Why |
|---|---|---|
| Target tenor | 30 calendar days | Matches CBOE VIX convention |
| Data window | 2017-01-01 to 2023-12-31 | Bounded by Databento OPRA history cost; covers Feb 2018 (Volmageddon), Mar 2020 (COVID), and 2022 |
| Underlying | SPX (`^GSPC` via yfinance) | Free, daily OHLC |
| Risk-free rate | FRED `DGS3MO` (3M Treasury), single rate for both near/next legs | Free; simplification vs. VIX's two-point yield-curve interpolation |
| Option prices | Last-trade daily close, not bid/ask mid | True quote data (Databento `cbbo`) cost ~$87/year alone — unaffordable at this project's ~$105 credit budget. Mitigated by a minimum-volume liquidity filter and a minimum-volume gate on forward/ATM-strike selection |
| Option chain breadth | Standard monthly SPX expiries only (`SPX.OPT` parent symbol); no SPXW weeklies | Same budget constraint — weeklies would have ~4x'd the pull cost |
| Realized variance | Forward 30-calendar-day close-to-close log returns, annualized by `252/n` (n = actual trading days in that window) | Standard estimator; Parkinson/Garman-Klass cross-checked as robustness |
| VRP | `implied_variance(t) − realized_variance(t→t+30)`, strictly forward-looking | No look-ahead: realized side only ever uses returns after t |
| Strategy sizing | Rolling short 30-day variance swaps, fixed *aggregate* vega notional, sized per-entry as `vega_notional / n` (n ≈ 21 trading days) since ~n tranches are open at once | Without the 1/n split, aggregate exposure would be ~n× the stated target |
| Strategy costs | `TRANSACTION_COST_BPS = 5.0` + `2 × BID_ASK_HALF_SPREAD_BPS = 5.0` = 10 bps of vega notional, charged once at entry | Placeholders, not real cost data — flagged explicitly in `config.py`; revisit if real bid-ask data becomes available |
| Strategy risk control | Tail stop: skip new entries when trailing (backward-looking, no look-ahead) 10-day realized vol > 35% | ~2.2 std above the full-sample mean trailing realized vol (14.3%, std 9.2%) — existing tranches still mature normally; only fresh issuance is paused |
| Strategy P&L accrual | Each tranche's lifetime payoff (`variance_notional × VRP`) is amortized linearly across the trading days it's held | Simplification vs. true daily variance-swap mark-to-market, which has its own day-to-day volatility |

## Implied Variance Validation

Synthetic 30-day implied volatility vs. the real CBOE VIX, 2017-2023, 1,676
trading days. Reproduce: `python scripts/validate_full_history.py`.

| Metric | Value |
|---|---|
| Mean abs error | 0.568 vol points |
| Median abs error | 0.345 vol points |
| RMSE | 1.134 vol points |
| 95th percentile abs error | 1.645 vol points |
| Max abs error | 18.94 vol points (single day: 2017-12-20) |
| Correlation with VIX | 0.9909 |

Per-year mean abs error (no regime where the replication breaks down):

| Year | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---|---|---|---|---|---|---|
| Mean abs error | 0.52 | 0.47 | 0.32 | 0.76 | 0.58 | 0.68 | 0.64 |

**Three correctness bugs were found and fixed during this validation:**

1. **Stale-tick corruption of forward selection (2020-03-16).** A single 1-lot
   trade printed a deep-ITM put at $0.08 (vs. $700-900 every other day that
   month). Because the forward/ATM-strike is chosen by minimizing `|C-P|`
   across strikes, that one bad tick made a strike near 3300 look "most ATM"
   when the real forward was near 2390 — corrupting the whole day's put/call
   split. Fixed by requiring both legs to clear a minimum volume
   (`MIN_VOLUME_FOR_FORWARD = 10`) before a strike is eligible to anchor the
   forward calculation.
2. **Invalid extrapolation when the bracket doesn't straddle 30 days
   (worst case: 2023-05-16, synthetic vol > 1500%).** Without SPXW weeklies,
   the nearest available monthly expiry sometimes already exceeds 30 days.
   The time-interpolation formula assumes `near_dte ≤ 30 ≤ next_dte`; when
   that's violated, the weights go outside `[0,1]` and amplify the gap
   between the two legs without bound. Fixed in
   `implied_variance._select_bracket_expiries` by requiring a genuine
   straddle and dropping the date otherwise.
3. **`instrument_id` reuse by the exchange (worst case: 2023-12-20, error
   836 vol points).** Databento/OPRA recycle numeric `instrument_id` values
   for entirely different contracts over time. Joining daily bars to a
   time-collapsed `instrument_id → (strike, expiry, right)` table meant some
   bars got matched to the wrong contract spec (confirmed directly: one
   `instrument_id` our definitions table said was "strike 4080 call" was, on
   the actual trade date, a "strike 3820 put" per the bar's own embedded
   `symbol` field). Fixed in `cleaning.load_panel` by parsing each bar's
   `symbol` field directly instead of joining on `instrument_id`.

## Realized Variance

Forward 30-day realized variance from SPX close-to-close returns.
Cross-checked against Parkinson and Garman-Klass range-based estimators:
correlation with close-to-close is 0.96 (Parkinson) and 0.95 (Garman-Klass)
— all three estimators agree directionally. Sanity-checked magnitudes:
~7-8% in calm June 2017, up to 96% in the Feb-Mar 2020 COVID window.

## Variance Risk Premium

`implied_variance(t)` minus the variance realized over the following 30
days, 2017-2023, 1,676 days. Reproduce: `python scripts/compute_vrp.py`.

| Metric | Value |
|---|---|
| Mean VRP | **+3.75 vol points** |
| Median VRP | +4.86 vol points |
| Std dev of VRP | 9.01 vol points |
| % of days VRP > 0 | **83.7%** |
| Mean implied vol | 19.52% |
| Mean realized vol | 15.77% |

**Regime breakdown** — VRP is positive on average everywhere, but
meaningfully thinner and less reliable in crisis years:

| Regime | Mean VRP | Median VRP | % positive | Days |
|---|---|---|---|---|
| Calm/other | +4.32 | +4.92 | 88.0% | 1195 |
| 2020 (COVID) | +2.28 | +9.52 | 76.0% | 242 |
| 2022 (bear market) | +2.37 | +2.36 | 69.9% | 239 |

**Worst single days** (all within Feb 14 – Mar 4, 2020): VRP as negative as
**−72.3 vol points** on 2020-02-21, where implied vol sat at 17.3% while the
following 30 days realized 89.6% — implied vol did not come close to
pricing the COVID crash in advance. VRP turns sharply negative around vol
spikes rather than smoothly absorbing them.

## Cost-Aware Short-Variance Carry

Rolling short 30-day variance swaps (see assumptions above for sizing, costs,
and the tail-stop). Reproduce: `python scripts/run_strategy.py`. Returns are
P&L as a fraction of the fixed vega-notional risk base.

| Metric | Gross | Net |
|---|---|---|
| CAGR | 19.3% | 18.0% |
| Annualized vol | 9.23% | 9.22% |
| Sharpe | 1.96 | 1.84 |
| Max drawdown | −70.6% | −70.6% |
| Worst day | −5.63% | −5.63% |
| CVaR (5%) | −1.63% | −1.64% |
| Total return (2017-2023) | +247% | +221% |

**Regime breakdown (net):**

| Regime | CAGR | Days |
|---|---|---|
| Calm/other | +40.7% | 1274 |
| 2020 (COVID) | **−50.9%** | 253 |
| 2022 (bear market) | +16.8% | 251 |

Max drawdown (−70.6%) bottoms on **2020-04-23**; the 10 worst single days are
all between Feb 27 and Mar 11, 2020. Feb 2018 (Volmageddon) also shows a
real, visible drawdown — cumulative −14.8% by late Feb 2018 — but far
smaller than COVID's. This is a genuine distinction, not an inconsistency:
this strategy is exposed to *realized variance over the following 30 days*,
not daily-rebalanced front-month VIX futures. Volmageddon was primarily a
violent one-day repricing of near-term implied vol (what destroyed
daily-rebalanced products like XIV); it did not translate into anywhere
near as much *sustained* 30-day realized variance as COVID did.

The tail stop (skip new entries when trailing realized vol > 35%) fired on
62 of 1,676 candidate days, all within the COVID window — it stops *new*
exposure from being added once a crisis is already visible, but cannot
protect tranches already opened during the preceding calm period. That
residual exposure is the entire source of the COVID drawdown above — a
structural limitation of a tail stop, as opposed to a hedge.

## Limitations

- No bid/ask quotes — last-trade close only (see the stale-tick mitigation above).
- No SPXW weeklies — coarser near/next bracketing than the official VIX
  methodology (affected dates are dropped, not extrapolated; see the
  bracket-extrapolation mitigation above).
- Single 3M T-bill rate proxy for both near/next legs, not a full yield-curve
  interpolation.
- Data window is 2017-2023, not extended to the present, due to the
  Databento credit budget ($92.61 of ~$105 spent on the full SPX option
  chain pull; see the spend ledger at `data/raw/databento/.spend_ledger.json`).
- Transaction-cost and bid-ask bps are placeholders, not measured real
  costs (see assumptions table above).
- Strategy P&L is a linear-amortization approximation of true variance-swap
  mark-to-market (see assumptions table above) — not a delta-hedged options
  simulation, so it doesn't capture intraday/path-dependent hedging P&L.
- A single day's loss can exceed 100% of the fixed risk-capital base at this
  position sizing; `backtest.py` floors compounding NAV at zero once wiped
  out (matching real-world liquidation behavior) rather than letting NAV go
  negative and compounding through sign flips.

## Reproducibility

```
python scripts/fetch_databento.py        # SPX option chains (skips cached chunks; costs real money on first run)
python scripts/validate_full_history.py  # builds + validates the synthetic implied-vol series vs VIX
python scripts/compute_vrp.py            # realized variance and VRP
python scripts/run_strategy.py           # cost-aware short-variance carry, gross vs. net
```
