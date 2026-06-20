"""Driver for pulling SPX option data from Databento, slice by slice.

Each (start, end) window is pulled for both the `definition` schema
(instrument_id -> strike/expiry/type) and the price schema (default
ohlcv-1d). Every pull goes through fetch_range's cache-check + cost
estimate + spend-ledger + approval gate — see src/vrp/ingest/databento.py.

Usage: edit WINDOWS below and run with `python scripts/fetch_databento.py`.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_RAW_DIR
from src.vrp.ingest import databento

SYMBOLS = ["SPX.OPT"]


def pull_window(start: str, end: str, label: str, assume_yes: bool = False) -> None:
    out_dir = DATA_RAW_DIR / "databento"

    for schema in ["definition", "ohlcv-1d"]:
        out_path = out_dir / f"{schema}_{label}.parquet"
        databento.fetch_range(
            symbols=SYMBOLS,
            start=start,
            end=end,
            out_path=out_path,
            schema=schema,
            assume_yes=assume_yes,
        )


def year_windows(start_year: int, end_year: int) -> list[tuple[str, str, str]]:
    """One window per calendar year. Fine through 2018; later years have enough
    listed contracts (more weeklies over time) that even a full year times out
    the streaming gateway — see quarter_windows for 2019+.
    """
    return [
        (f"{y}-01-01", f"{y + 1}-01-01", str(y))
        for y in range(start_year, end_year + 1)
    ]


def quarter_windows(start_year: int, end_year: int) -> list[tuple[str, str, str]]:
    bounds = ["01-01", "04-01", "07-01", "10-01"]
    windows = []
    for y in range(start_year, end_year + 1):
        for q in range(4):
            start = f"{y}-{bounds[q]}"
            end = f"{y}-{bounds[q + 1]}" if q < 3 else f"{y + 1}-01-01"
            windows.append((start, end, f"{y}-Q{q + 1}"))
    return windows


if __name__ == "__main__":
    WINDOWS = year_windows(2017, 2018) + quarter_windows(2019, 2023)
    for start, end, label in WINDOWS:
        print(f"\n=== {label} ({start} -> {end}) ===")
        pull_window(start, end, label, assume_yes=True)

    print(f"\nCumulative Databento spend so far: ${databento.cumulative_spend_usd():.4f}")
