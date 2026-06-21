# Variance Risk Premium & Variance-Swap Replication

Replicates a 30-day SPX variance swap from option strips (model-free implied
variance, CBOE VIX methodology), measures the variance risk premium against
realized variance, and backtests a cost-aware short-variance carry. The
implied-variance replication is validated against the real CBOE VIX (0.568
mean abs error, 0.9909 correlation, 2017-2023). See [RESULTS.md](RESULTS.md)
for full results, assumptions, and limitations.

## Setup

```
python3.11 -m venv .venv   # already created; see .venv/
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # fill in DATABENTO_API_KEY
```

## Run

```
python run.py          # full pipeline: fetch -> validate -> VRP -> strategy
streamlit run app.py   # interactive dashboard
```

`run.py` chains the four scripts below in order. Each is also independently
runnable (see [RESULTS.md](RESULTS.md)'s Reproducibility section):

```
python scripts/fetch_databento.py        # SPX option chain pull (cost-gated; cached chunks are free to re-run)
python scripts/validate_full_history.py  # implied-variance replication, validated against real VIX
python scripts/compute_vrp.py            # realized variance + variance risk premium
python scripts/run_strategy.py           # cost-aware short-variance carry backtest
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
