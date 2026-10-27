#!/usr/bin/env python3
"""Download fresh public snapshots from the Dutch Algorithm Register.

The repository already includes the exact 2026-10-28 inputs used by the paper.
Running this script later retrieves the website's then-current content; it does
not recreate the archived paper snapshot. Use a new snapshot date to avoid
overwriting the archived inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
URLS = {
    "current": "https://algoritmes.overheid.nl/api/downloads/NLD?filetype=csv",
    "history": "https://algoritmes.overheid.nl/api/downloads/history/NLD?filetype=csv",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, help="New snapshot label, YYYY-MM-DD")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    datetime.strptime(args.snapshot, "%Y-%m-%d")
    if args.snapshot == "2026-10-28":
        raise SystemExit("该日期是论文归档快照。请选择新日期，避免覆盖原始证据。")

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    manifest = {
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_label": args.snapshot,
        "language": "NLD",
        "files": [],
    }
    for kind, url in URLS.items():
        target = data_dir / f"algorithms_{kind}_{args.snapshot}.csv"
        response = requests.get(url, timeout=args.timeout)
        response.raise_for_status()
        target.write_bytes(response.content)
        frame = pd.read_csv(target, dtype={"algorithm_id": str})
        record = {
            "kind": kind,
            "url": url,
            "file": str(target.relative_to(ROOT)),
            "bytes": target.stat().st_size,
            "sha256": sha256(target),
            "rows": len(frame),
            "columns": len(frame.columns),
            "unique_algorithm_ids": int(frame["algorithm_id"].nunique()),
        }
        manifest["files"].append(record)
        print(json.dumps(record, ensure_ascii=False))
    manifest_path = data_dir / f"source_manifest_{args.snapshot}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
