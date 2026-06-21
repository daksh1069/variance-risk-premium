"""Central configuration for the VRP / variance-swap replication pipeline.

All tunables live here so RESULTS.md and the dashboard can report exactly
what assumptions produced a given number.
"""

from pathlib import Path

# --- Paths -------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent
DATA_RAW_DIR = ROOT_DIR / "data" / "raw"
DATA_CACHE_DIR = ROOT_DIR / "data" / "cache"
DATA_EXTERNAL_DIR = ROOT_DIR / "data" / "external"
FIGURES_DIR = ROOT_DIR / "figures"

# --- Universe / dates ----------------------------------------------------
UNDERLYING_TICKER = "^GSPC"  # SPX via yfinance for realized-variance/spot
SPY_TICKER = "SPY"
START_DATE = "2013-01-01"  # bounded by OPRA history on Databento
END_DATE = None  # None = through latest available

# --- Replication target ---------------------------------------------------
TARGET_TENOR_DAYS = 30

# --- Databento -------------------------------------------------------------
DATABENTO_DATASET = "OPRA.PILLAR"
DATABENTO_SPX_SYMBOLS = ["SPX.OPT"]  # parent symbol for SPX option chain; confirm via metadata.list_symbols
DATABENTO_SCHEMA = "ohlcv-1d"  # cheapest schema sufficient for daily EOD replication
# Hard safety cap: code must refuse any pull whose estimated cost (from
# databento's metadata.get_cost) would push cumulative spend past this,
# leaving a buffer below the ~$105 remaining account credit.
DATABENTO_MAX_SPEND_USD = 95.00  # covers the approved $90.17 full pull + $2.44 pilot = $92.61, leaving buffer below the $105 credit
DATABENTO_SPEND_LEDGER = DATA_RAW_DIR / "databento" / ".spend_ledger.json"

# --- Strategy costs ---------------------------------------------------------
TRANSACTION_COST_BPS = 5.0  # placeholder; revisit once strategy is built
BID_ASK_HALF_SPREAD_BPS = 2.5  # placeholder

# --- Option quality filters --------------------------------------------
MIN_OPTION_PRICE = 0.05
MONEYNESS_BAND = (0.5, 1.5)  # strike / spot bounds for inclusion
