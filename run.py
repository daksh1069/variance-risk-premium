"""End-to-end pipeline entry point: chains all four phase scripts in order.

    python run.py

Each underlying script is independently runnable too (see RESULTS.md's
Reproducibility section) — this just sequences them. fetch_databento.py is
safe to re-run: every chunk for 2017-2023 is already cached locally, so this
will not re-spend against the Databento credit (see
data/raw/databento/.spend_ledger.json) unless that cache is deleted.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = [
    "scripts/fetch_databento.py",
    "scripts/validate_full_history.py",
    "scripts/compute_vrp.py",
    "scripts/run_strategy.py",
]

if __name__ == "__main__":
    for step in STEPS:
        print(f"\n{'=' * 70}\n=== {step}\n{'=' * 70}")
        subprocess.run([sys.executable, str(ROOT / step)], check=True, cwd=ROOT)

    print("\nDone. Run `streamlit run app.py` for the dashboard.")
