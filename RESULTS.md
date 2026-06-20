# Results

Running results document, updated phase by phase. Every number below is
reproducible from the scripts cited next to it — nothing here is hand-typed
or rounded up from a different run.

**Status:** Phases 0-4 complete and validated. Phase 5 (cost-aware short-vol
carry) and Phase 6 (dashboard) not yet built.

## Assumptions (read before trusting anything below)

| Assumption | Value | Why |
|---|---|---|
| Target tenor | 30 calendar days | Matches CBOE VIX convention |
| Data window | 2017-01-01 to 2023-12-31 | Bounded by Databento OPRA history cost; covers Feb 2018 (Volmageddon), Mar 2020 (COVID), and 2022 |
| Underlying | SPX (`^GSPC` via yfinance) | Free, daily OHLC |
| Risk-free rate | FRED `DGS3MO` (3M Treasury), single rate for both near/next legs | Free; simplification vs. VIX's two-point yield-curve interpolation |
| Option prices | Last-trade daily close, **not bid/ask mid** | True quote data (Databento `cbbo`) cost ~$87/year alone — unaffordable at this project's ~$105 credit budget. Mitigated by a minimum-volume liquidity filter and a minimum-volume gate on forward/ATM-strike selection (see bugs below) |
| Option chain breadth | Standard monthly SPX expiries only (`SPX.OPT` parent symbol); **no SPXW weeklies** | Same budget constraint — weeklies would have ~4x'd the pull cost |
| Realized variance | Forward 30-calendar-day close-to-close log returns, annualized by `252/n` (n = actual trading days in that window) | Standard estimator; Parkinson/Garman-Klass cross-checked as robustness |
| VRP | `implied_variance(t) − realized_variance(t→t+30)`, strictly forward-looking | No look-ahead: realized side only ever uses returns after t |

## Phase 2 — Implied Variance Validation (the project's correctness gate)

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
   straddle and dropping the date otherwise — honest under-coverage instead
   of a fabricated number.
3. **`instrument_id` reuse by the exchange (worst case: 2023-12-20, error
   836 vol points).** Databento/OPRA recycle numeric `instrument_id` values
   for entirely different contracts over time. Joining daily bars to a
   time-collapsed `instrument_id → (strike, expiry, right)` table meant some
   bars got matched to the wrong contract spec (confirmed directly: one
   `instrument_id` our definitions table said was "strike 4080 call" was, on
   the actual trade date, a "strike 3820 put" per the bar's own embedded
   `symbol` field). Fixed in `cleaning.load_panel` by parsing each bar's
   `symbol` field directly instead of joining on `instrument_id`.

## Phase 3 — Realized Variance

Forward 30-day realized variance from SPX close-to-close returns.
Cross-checked against Parkinson and Garman-Klass range-based estimators:
correlation with close-to-close is 0.96 (Parkinson) and 0.95 (Garman-Klass)
— all three estimators agree directionally. Sanity-checked magnitudes:
~7-8% in calm June 2017, up to 96% in the Feb-Mar 2020 COVID window.

## Phase 4 — Variance Risk Premium

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
pricing the COVID crash in advance. This matches the brief's stated
expectation: VRP turns sharply negative around vol spikes rather than
smoothly absorbing them.

## Limitations (disclosed, not hidden)

- No bid/ask quotes — last-trade close only (see Phase 2 bug #1's mitigation).
- No SPXW weeklies — coarser near/next bracketing than the official VIX
  methodology (see Phase 2 bug #2's mitigation: affected dates are dropped,
  not extrapolated).
- Single 3M T-bill rate proxy for both near/next legs, not a full yield-curve
  interpolation.
- Data window is 2017-2023, not extended to the present, due to the
  Databento credit budget ($92.61 of ~$105 spent on the full SPX option
  chain pull; see the spend ledger at `data/raw/databento/.spend_ledger.json`).

## Reproducibility

```
python scripts/fetch_databento.py        # SPX option chains (skips cached chunks; costs real money on first run)
python scripts/validate_full_history.py  # builds + validates the synthetic implied-vol series vs VIX
python scripts/compute_vrp.py            # Phase 3 + 4: realized variance and VRP
```
