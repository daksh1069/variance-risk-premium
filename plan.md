# PROJECT BRIEF — Variance Risk Premium & Variance-Swap Replication

> **For an agent (Claude Code / Cowork) building this from scratch.** This is a fresh
> project. The goal is honest, reproducible, derivatives-grounded results plus an
> interactive Streamlit dashboard. Correctness and reproducibility matter more than
> impressive numbers — the headline deliverable is a *replication that is either right
> or not*, not a fragile alpha figure.

---

## 0. Quick start — paste this to Claude Code

```
Read PROJECT_BRIEF.md at the repo root — it's the full spec. We're building a
variance risk premium / variance-swap replication study on SPX, plus a Streamlit
dashboard, from scratch.

Before writing code (nothing exists yet, so this is mostly planning), propose:
1. A repo structure and the phased plan from the brief
   (data -> implied variance -> realized variance -> VRP -> cost-aware carry -> dashboard).
2. The exact data sources you'll use given I have Bloomberg Terminal and Databento
   access (and free fallbacks like CBOE VIX history and yfinance for SPX/SPY),
   plus any access or files you need from me.
3. Which phase you'll build first and how you'll validate it.

Then STOP and wait for my go-ahead before building.

Once approved: work phase by phase on a feature branch, keep a running RESULTS.md,
and make each phase runnable on its own. Validate the implied-variance engine against
the actual VIX before trusting anything downstream.

Hard rules: pin dependencies; model transaction and bid-ask costs and report gross
AND net; no look-ahead (point-in-time option data); document every assumption; and
never fabricate or round up a metric — every number must be reproducible, and if it
can't be, drop it and say so. Deliverables: a reproducible pipeline, a RESULTS.md,
and a Streamlit dashboard (`streamlit run app.py`).

Start with the plan now.
```

---

## 1. What we're building, and why

Replicate a **30-day variance swap** from a strip of SPX options (the *model-free
implied variance* integral — the same math underneath the VIX), measure the
**variance risk premium (VRP)** = implied minus realized variance, and evaluate a
**cost-aware short-volatility carry**. Everything is surfaced in an interactive
**Streamlit dashboard**.

Why this project: it shows you can replicate a derivative from first principles, it
sits at the core of how every volatility desk thinks (implied vs. realized), and the
result is robust and well-documented — short vol earns a premium but is punished in
2020 / 2022, which you *quantify* rather than hide. It also reuses an existing
options-data pipeline, so it's fast to a polished result.

**Owner:** Daksh Kumar (MS Financial Mathematics, NC State).

---

## 2. Core concepts (brief)

- **Variance swap:** a contract paying realized variance minus a fixed strike. Its
  fair strike is replicable, model-free, from a continuum of option prices.
- **Model-free implied variance:** the fair variance strike computed from an option
  strip via the standard replication integral (this is exactly the CBOE VIX
  construction — use the VIX white paper as the reference implementation template).
- **Realized variance:** variance actually realized by the underlying over a window,
  from returns.
- **Variance risk premium (VRP):** implied variance minus subsequently realized
  variance. Positive on average (sellers of vol get paid for bearing tail risk).
- **Short-vol carry:** systematically selling variance/options to harvest the VRP —
  high Sharpe in calm regimes, severe drawdowns in vol spikes. The tail *is* the story.

---

## 3. Scope (keep it tight — MVP first)

**In scope:**
- Single underlying: **SPX** (use SPY / VIX for validation and free fallbacks).
- Daily end-of-day data.
- One constant-maturity tenor: **~30-day**.
- One short-vol strategy variant + risk controls.
- Streamlit dashboard.

**Explicitly out of scope (optional stretch only, after the MVP works):**
- Intraday / high-frequency data.
- Multiple underlyings or term-structure surfaces.
- Exotic or rough-volatility models.
- Live / real-time trading.

---

## 4. Data

| Need | Source | Notes |
|---|---|---|
| SPX option chain history (close/mid, strike, expiry, type, IV if available) | **Bloomberg / Databento** (you have access) | The key input for the replication integral. |
| Underlying level (SPX / SPY daily close) | yfinance (free) or Databento | For realized variance + moneyness. |
| **VIX history** | CBOE (free) | Ground-truth to validate the synthetic 30-day implied vol. |
| Risk-free rate (3M T-bill / OIS) | FRED (free) | For discounting in the replication. |

- Bracket the 30-day point with the two nearest expiries and interpolate to constant
  maturity (VIX-style near/next term).
- Apply basic option-quality filters: positive prices, drop zero-bid/illiquid strikes,
  reasonable moneyness band.
- **Point-in-time only:** use each date's option snapshot as-of that date — no
  look-ahead.

---

## 5. Build plan (phased — each phase must run on its own)

**Phase 0 — Setup.** Repo structure, `requirements.txt`/env, a `config.py` (tenor,
cost bps, date range), `README` with the run command. Get a tiny date-slice flowing
end-to-end before scaling up.

**Phase 1 — Data layer.** Ingest and clean option chains into a tidy per-date panel;
coverage and arbitrage sanity checks (positive prices, monotonicity). Persist a cached
clean dataset.

**Phase 2 — Implied variance (the replication).** Implement model-free implied
variance per the CBOE VIX methodology: the strike-strip integral for the near and next
term, interpolated to a constant 30-day tenor. Output a synthetic 30-day implied vol
series. **Validate against the actual VIX** — they should track closely; report the
tracking error. *This is the project's correctness gate — do not proceed until it
passes.*

**Phase 3 — Realized variance.** Rolling/forward 30-day realized variance from
underlying returns (close-to-close; optionally Parkinson / Garman–Klass as a
robustness check).

**Phase 4 — Variance risk premium.** Compute VRP (the forward-looking version:
today's implied vs. the *next* 30 days' realized). Time series, summary stats, and a
regime breakdown (calm vs. 2020 / 2022).

**Phase 5 — Cost-aware short-vol carry.** A simple, honest strategy: systematically
short the 30-day variance (variance-short or a delta-hedged short-straddle proxy),
sized to fixed vega/risk, **with transaction costs, bid-ask, and a position cap or
tail stop.** Report **gross and net** Sharpe, CAGR, vol, max drawdown, worst day, and
tail (CVaR), full-sample with regime highlights. Show the blowups — don't smooth them.

**Phase 6 — Streamlit dashboard.** See §6.

---

## 6. Streamlit dashboard spec

`streamlit run app.py`. Sections:

- **Overview:** metric cards — average VRP, % of time VRP positive, strategy net
  Sharpe, max drawdown.
- **Implied vs. Realized:** time-series chart with regime shading (2020, 2022).
- **VRP:** time series + distribution histogram.
- **Replication validation:** synthetic 30-day implied vol vs. actual VIX, with the
  tracking-error stat displayed.
- **Snapshot:** option smile / term structure for a user-selected date.
- **Strategy:** equity curve (gross vs. net toggle), drawdown chart, monthly-returns
  heatmap, metrics table.

**Sidebar controls:** date range, target tenor (DTE), transaction-cost (bps) slider,
position-sizing / cap, realized-vol estimator choice, gross/net toggle.

**Tech:** `streamlit` + `plotly`; cache data loads (`@st.cache_data`); progressive
rendering so the UI isn't blocked on a full recompute.

---

## 7. Deliverables

1. Reproducible pipeline — one command runs end-to-end.
2. `RESULTS.md` containing: VRP summary stats; the synthetic-vs-actual-VIX tracking
   error; a **gross-vs-net** strategy metrics table; the regime breakdown; and an
   explicit **assumptions block** (cost bps, bid-ask, tenor, sizing, data window).
3. The Streamlit dashboard.
4. Key figures saved to `/figures`.

---

## 8. Guardrails (lessons from the last project)

- **No fabricated or rounded-up numbers** — everything reproducible from code; if it
  can't be reproduced, drop it.
- **Costs modeled** (bps + bid-ask); always report gross *and* net.
- **No look-ahead** — point-in-time option snapshots; keep today's implied strictly
  separate from forward-realized.
- **Validate before trusting:** the implied-variance engine must track the VIX before
  any downstream result is believed.
- Document every assumption inline; show drawdowns honestly.

---

## 9. Sanity-check expectations (for validation — do NOT hardcode these)

- The synthetic 30-day implied vol should track the VIX closely; a large gap means a
  bug in the replication.
- VRP is positive on average (implied typically exceeds realized by a few vol points)
  and turns sharply negative around vol spikes.
- Short-vol carry: attractive Sharpe in calm regimes, severe drawdowns around
  Feb 2018 and Mar 2020 — the tail is the headline, not a footnote.

---

## 10. Résumé payoff (target bullets — fill the bracketed values from real output)

- Replicated a 30-day variance swap from SPX option strips (model-free implied
  variance), validating the synthetic index against the CBOE VIX to within [X] vol pts.
- Measured the variance risk premium over [period]; quantified its average level,
  regime dependence, and tail behavior.
- Backtested a cost-aware short-variance carry: net Sharpe [X], max drawdown [Y], with
  the 2020 / 2022 tail explicitly characterized.
- Built an interactive Streamlit dashboard for implied-vs-realized volatility, the
  variance risk premium, and strategy performance.

---

## 11. Tech stack & run

- **Python:** numpy, pandas, scipy, plotly, streamlit; yfinance / databento for data.
- `pip install -r requirements.txt`
- Pipeline: `python run.py` (or a documented entry point)
- Dashboard: `streamlit run app.py`