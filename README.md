# Variance Risk Premium & Variance-Swap Replication

Replicates a 30-day SPX variance swap from option strips (model-free implied
variance, CBOE VIX methodology), measures the variance risk premium against
realized variance, and backtests a cost-aware short-variance carry. See
[plan.md](plan.md) for the full spec and phased build plan.

## Setup

```
python3.11 -m venv .venv   # already created; see .venv/
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # fill in DATABENTO_API_KEY
```

## Run

```
python run.py        # full pipeline (not yet implemented — Phase 0 in progress)
streamlit run app.py  # dashboard (Phase 6)
```

## Data sources

- SPX option chains: Databento (`OPRA.PILLAR` dataset, since 2013). Every pull
  is preceded by a cost estimate checked against a spend ledger
  (`data/raw/databento/.spend_ledger.json`) capped at `DATABENTO_MAX_SPEND_USD`
  in `config.py` — see `src/vrp/ingest/databento.py`.
- VIX history: free CBOE CSV, for validating the synthetic implied-vol series.
- Risk-free rate: free FRED CSV (3M Treasury).
- SPX/SPY underlying: yfinance.
- Bloomberg (Excel Add-in only, no local API) is used only for ad hoc
  spot-checks, not bulk ingestion.

## Status

Phase 0 (setup) in progress. See `plan.md` §5 for the phase list and
`RESULTS.md` (once it exists) for validated output.
