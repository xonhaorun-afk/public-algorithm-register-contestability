#!/usr/bin/env python3
"""Restore the paper's exact public CSV snapshots and enforce their hashes.

The live official endpoints matched the archived bytes during remote verification.
If the provider later changes either file, this script fails closed instead of
silently substituting a newer snapshot for the paper's evidence.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    (
        "https://algoritmes.overheid.nl/api/downloads/NLD?filetype=csv",
        ROOT / "data/algorithms_current_2026-10-28.csv",
        "062550033289976baa6ee2b75a923c991c984e4ccf9d676297b434a374aad01f",
    ),
    (
        "https://algoritmes.overheid.nl/api/downloads/history/NLD?filetype=csv",
        ROOT / "data/algorithms_history_2026-10-28.csv",
        "83d3cbafb93146c5c39fead5cb8de2ba75c859e24d0e5120c56d4f5115daf54f",
    ),
]

for url, target, expected in FILES:
    response = requests.get(url, timeout=240)
    response.raise_for_status()
    actual = hashlib.sha256(response.content).hexdigest()
    if actual != expected:
        raise SystemExit(
            f"Hash mismatch for {url}: expected {expected}, got {actual}. "
            "The live endpoint no longer matches the archived paper snapshot."
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.content)
    print(f"Verified {target.relative_to(ROOT)}: {actual}")
