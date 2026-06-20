"""SPX option chain ingestion from Databento (OPRA dataset).

Safety contract:
1. If the requested slice is already cached on disk, skip straight to it —
   no cost estimate, no API call, no spend.
2. Otherwise, always call Databento's own metadata.get_cost first and check
   it against the running spend ledger / cap.
3. Never fetch without a typed "yes" at an interactive prompt, shown after
   the estimate. assume_yes=True exists only for non-interactive/scripted
   contexts and should be treated as dangerous — it skips the
   human-in-the-loop check.

Uses the batch job API (submit/poll/download), not the synchronous streaming
get_range API: multi-month SPX.OPT pulls reliably hit a 504 gateway timeout
on the streaming endpoint once the chain gets large (more listed strikes in
later years), even for single-quarter windows. Batch jobs have no such
timeout — Databento processes them server-side and we poll for completion.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import databento as db
import pandas as pd
from dotenv import load_dotenv
import os

from config import (
    DATABENTO_DATASET,
    DATABENTO_MAX_SPEND_USD,
    DATABENTO_SCHEMA,
    DATABENTO_SPEND_LEDGER,
)

load_dotenv()

BATCH_POLL_INTERVAL_S = 10
BATCH_TIMEOUT_S = 1800
RETRYABLE_ATTEMPTS = 6
RETRYABLE_BACKOFF_S = 15


def _with_retries(fn, what: str):
    """Databento's gateway returns transient 502/504s under this account/dataset
    right now (seen during this project's own pulls). Retry a handful of times
    with backoff rather than aborting the whole multi-year job over a blip —
    but still raise after RETRYABLE_ATTEMPTS so a real, persistent failure
    doesn't get silently swallowed.
    """
    last_exc = None
    for attempt in range(1, RETRYABLE_ATTEMPTS + 1):
        try:
            return fn()
        except db.common.error.BentoServerError as exc:
            last_exc = exc
            print(f"[databento] {what} failed ({exc}), attempt {attempt}/{RETRYABLE_ATTEMPTS}, retrying...")
            time.sleep(RETRYABLE_BACKOFF_S)
    raise last_exc


class BudgetExceededError(RuntimeError):
    pass


def _client() -> db.Historical:
    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        raise RuntimeError(
            "DATABENTO_API_KEY not set. Put it in a local .env file (see .env.example); "
            "never pass it on the command line or commit it."
        )
    return db.Historical(key)


def _read_ledger() -> dict:
    if not DATABENTO_SPEND_LEDGER.exists():
        return {"total_spend_usd": 0.0, "entries": []}
    return json.loads(DATABENTO_SPEND_LEDGER.read_text())


def _write_ledger(ledger: dict) -> None:
    DATABENTO_SPEND_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    DATABENTO_SPEND_LEDGER.write_text(json.dumps(ledger, indent=2))


def cumulative_spend_usd() -> float:
    return _read_ledger()["total_spend_usd"]


def estimate_cost(
    symbols: list[str],
    start: str,
    end: str,
    schema: str = DATABENTO_SCHEMA,
    dataset: str = DATABENTO_DATASET,
    stype_in: str = "parent",
) -> float:
    """Return Databento's own dollar cost estimate for a pull, without fetching anything."""
    client = _client()
    cost = _with_retries(
        lambda: client.metadata.get_cost(
            dataset=dataset,
            symbols=symbols,
            schema=schema,
            start=start,
            end=end,
            stype_in=stype_in,
        ),
        "metadata.get_cost",
    )
    return float(cost)


def _find_existing_job(client: db.Historical, dataset: str, symbols: list[str], schema: str, start: str, end: str) -> str | None:
    """Look for an already-submitted job matching these exact parameters.

    If a previous run submitted the job and then crashed/errored before
    downloading it (e.g. a transient gateway error while polling), we must
    resume that job rather than submit a duplicate — Databento bills on
    submission, so resubmitting would pay twice for the same data.
    """
    symbols_str = ",".join(symbols) if isinstance(symbols, list) else symbols
    target_start, target_end = pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC")
    for j in client.batch.list_jobs(states="queued,processing,done"):
        if j.get("dataset") != dataset or j.get("schema") != schema or j.get("symbols") != symbols_str:
            continue
        try:
            if pd.Timestamp(j["start"]) != target_start or pd.Timestamp(j["end"]) != target_end:
                continue
        except (KeyError, ValueError):
            continue
        return j["id"]
    return None


def fetch_range(
    symbols: list[str],
    start: str,
    end: str,
    out_path,
    schema: str = DATABENTO_SCHEMA,
    dataset: str = DATABENTO_DATASET,
    stype_in: str = "parent",
    force_refetch: bool = False,
    assume_yes: bool = False,
) -> float:
    """Fetch a slice of SPX option data, gated by a local cache, a cost
    estimate, the spend ledger/cap, and an interactive typed approval.

    Returns the cost in USD actually incurred (0.0 on a cache hit or a
    declined/dry-run estimate). Never spends without a human typing "yes",
    unless assume_yes=True is passed explicitly (scripted use only).
    """
    if out_path.exists() and not force_refetch:
        print(f"[databento] cache hit at {out_path} — skipping fetch, no cost incurred.")
        return 0.0

    estimated = estimate_cost(symbols, start, end, schema=schema, dataset=dataset, stype_in=stype_in)
    ledger = _read_ledger()
    projected_total = ledger["total_spend_usd"] + estimated

    print(f"[databento] estimated cost for {symbols} {start}->{end} ({schema}): ${estimated:.4f}")
    print(f"[databento] cumulative spend so far: ${ledger['total_spend_usd']:.4f}; "
          f"projected after this pull: ${projected_total:.4f} (cap: ${DATABENTO_MAX_SPEND_USD:.2f})")

    if projected_total > DATABENTO_MAX_SPEND_USD:
        raise BudgetExceededError(
            f"Pulling this would bring cumulative spend to ${projected_total:.4f}, "
            f"over the configured cap of ${DATABENTO_MAX_SPEND_USD:.2f}. Narrow the "
            f"request (fewer symbols / shorter range / cheaper schema) or raise "
            f"DATABENTO_MAX_SPEND_USD in config.py deliberately."
        )

    if not assume_yes:
        response = input(
            f"[databento] Type 'yes' to actually fetch this and spend ~${estimated:.4f}: "
        )
        if response.strip().lower() != "yes":
            print("[databento] not confirmed — dry run only, nothing fetched, ledger unchanged.")
            return 0.0

    client = _client()
    existing_job_id = _find_existing_job(client, dataset, symbols, schema, start, end)
    if existing_job_id:
        job_id = existing_job_id
        print(f"[databento] found existing job {job_id} for this exact request — resuming it instead of resubmitting.")
    else:
        job = client.batch.submit_job(
            dataset=dataset,
            symbols=symbols,
            schema=schema,
            start=start,
            end=end,
            stype_in=stype_in,
        )
        job_id = job["id"]
        print(f"[databento] submitted batch job {job_id}, polling every {BATCH_POLL_INTERVAL_S}s...")

    deadline = time.time() + BATCH_TIMEOUT_S
    state = None
    details: dict = {}
    while time.time() < deadline:
        details = _with_retries(lambda: client.batch.get_job_details(job_id), "get_job_details")
        state = details.get("state")
        if state == "done":
            break
        if state == "expired":
            raise RuntimeError(f"Batch job {job_id} expired before completing.")
        time.sleep(BATCH_POLL_INTERVAL_S)
    else:
        raise TimeoutError(
            f"Batch job {job_id} did not finish within {BATCH_TIMEOUT_S}s (last state={state})."
        )

    download_dir = out_path.parent / "_batch_downloads"
    downloaded = _with_retries(
        lambda: client.batch.download(job_id=job_id, output_dir=download_dir), "batch.download"
    )
    dbn_files = sorted(p for p in downloaded if p.name.endswith(".dbn.zst") or p.suffix == ".dbn")
    if not dbn_files:
        raise RuntimeError(f"Batch job {job_id} completed but no .dbn file was downloaded.")

    frames = [db.DBNStore.from_file(p).to_df() for p in dbn_files]
    data = pd.concat(frames).sort_index() if len(frames) > 1 else frames[0]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(out_path)

    actual_cost = details.get("cost_usd", estimated)
    actual_total = ledger["total_spend_usd"] + actual_cost
    ledger["total_spend_usd"] = actual_total
    ledger["entries"].append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "symbols": symbols,
            "start": start,
            "end": end,
            "schema": schema,
            "dataset": dataset,
            "estimated_cost_usd": estimated,
            "actual_cost_usd": actual_cost,
            "job_id": job_id,
            "out_path": str(out_path),
        }
    )
    _write_ledger(ledger)

    return actual_cost
