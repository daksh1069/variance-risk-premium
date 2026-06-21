"""Turn raw Databento ohlcv-1d/definition parquet files into a tidy per-date option panel."""

import pandas as pd

from config import MIN_OPTION_PRICE

# OPRA/Databento symbol format, e.g. "SPX   240119P03820000": root, padding,
# then YYMMDD + right (C/P) + 8-digit strike (scaled by 1000). Anchored on the
# end of the string so root padding doesn't matter.
SYMBOL_PATTERN = r"(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<right>[CP])(?P<strike>\d{8})$"


def load_panel(definition_path, ohlcv_path) -> pd.DataFrame:
    """Parse strike/expiry/right straight from each bar's own `symbol` field.

    Does not join on instrument_id: Databento/OPRA recycle
    instrument_id for entirely different contracts over time (confirmed by
    cross-checking a specific 2023-12-20 case — the ID our definitions table
    said was "strike 4080 call exp 2024-01-19" was, on that actual date, a
    "strike 3820 put exp 2024-01-19" per the bar's own embedded symbol).
    Joining bars to a time-collapsed instrument_id->spec table silently
    mixes up unrelated contracts and produced a >800-point synthetic VIX
    error before this fix. Parsing the per-record symbol string sidesteps the
    problem entirely, since Databento generates it correctly for that record.

    Columns: date, expiry, dte, right (C/P), strike, close, volume.
    No look-ahead: each row's close is that same row's date close, nothing else.
    """
    bars = pd.read_parquet(ohlcv_path).reset_index()
    parsed = bars["symbol"].str.extract(SYMBOL_PATTERN)

    bars["date"] = pd.to_datetime(bars["ts_event"]).dt.tz_localize(None).dt.normalize()
    bars["expiry"] = pd.to_datetime(
        "20" + parsed["yy"] + "-" + parsed["mm"] + "-" + parsed["dd"]
    ).dt.normalize()
    bars["dte"] = (bars["expiry"] - bars["date"]).dt.days
    bars["right"] = parsed["right"]
    bars["strike"] = parsed["strike"].astype(float) / 1000.0

    panel = bars[["date", "expiry", "dte", "right", "strike", "close", "volume"]].dropna(subset=["right", "strike"]).copy()

    # Some (date, expiry, right, strike) combinations carry more than one
    # instrument_id (separate matching-engine/listing records for the same
    # nominal contract, common from 2023 on with SPX 0DTE volume). Collapse
    # into one row: sum volume, volume-weight the price.
    dupe_keys = ["date", "expiry", "dte", "right", "strike"]
    panel["_notional"] = panel["close"] * panel["volume"]
    agg = panel.groupby(dupe_keys, as_index=False).agg(
        volume=("volume", "sum"), _notional=("_notional", "sum")
    )
    agg["close"] = agg["_notional"] / agg["volume"].replace(0, pd.NA)
    panel = agg.drop(columns="_notional")
    return panel


def apply_quality_filters(panel: pd.DataFrame) -> pd.DataFrame:
    """Drop strikes with no trade that day or a non-positive close.

    We don't have bid/ask (see databento.py docstring for why), so "no trade
    that day" (volume == 0) is our only available proxy for "stale/illiquid."
    """
    out = panel[(panel["volume"] > 0) & (panel["close"] >= MIN_OPTION_PRICE)].copy()
    return out


def full_strike_grid(definition_path) -> pd.DataFrame:
    """Every strike ever listed per expiry in this window, independent of whether
    it traded on any given day. Used to compute correct ΔK spacing and to find
    the genuine two-consecutive-missing-strike truncation point — using only
    the strikes that happened to trade that day (as apply_quality_filters does)
    silently inflates ΔK across any gap left by an untraded strike, which is
    exactly what blew up the 2020-03-16 variance estimate (see RESULTS.md).

    Does not dedupe by instrument_id first (see load_panel's
    docstring on ID recycling) — every (expiration, strike_price) pair across
    every definition record is used directly, since we only need the set of
    strikes that were ever listed for an expiry, not a clean ID mapping.
    """
    defn = pd.read_parquet(definition_path)
    defn["expiry"] = pd.to_datetime(defn["expiration"]).dt.tz_localize(None).dt.normalize()
    defn["strike"] = defn["strike_price"].astype(float)
    grid = defn[["expiry", "strike"]].drop_duplicates().sort_values(["expiry", "strike"])
    return grid
