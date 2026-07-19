"""Verifier for LEDGER-demo hash chains: library function + CLI.

Recomputes every SHA-256 link from genesis and fails on any gap, reordered,
removed, inserted, or modified entry. Optionally also checks that a data
file still matches the sha256 recorded in the ``data_ingested`` entry.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from .ledger import LedgerIntegrityError, load_entries, verify_entries


def verify_file(path: str | Path, data_path: str | Path | None = None) -> dict:
    entries = load_entries(path)
    verify_entries(entries)
    summary = {
        "ok": True,
        "entries": len(entries),
        "kinds": [e.kind for e in entries],
        "genesis_link": entries[0].previous_hash if entries else None,
        "head_hash": entries[-1].entry_hash if entries else None,
    }
    if data_path is not None:
        recorded = None
        for e in entries:
            if e.kind == "data_ingested":
                recorded = e.payload.get("sha256")
                break
        actual = hashlib.sha256(Path(data_path).read_bytes()).hexdigest()
        summary["data_sha256_recorded"] = recorded
        summary["data_sha256_actual"] = actual
        if recorded is None or recorded != actual:
            raise LedgerIntegrityError(
                "data file does not match the sha256 recorded in the ledger"
            )
        summary["data_match"] = True
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a LEDGER-demo hash chain.")
    parser.add_argument("ledger", help="path to ledger JSONL file")
    parser.add_argument("--data", help="optional CSV data file to check against data_ingested")
    parser.add_argument("--quiet", action="store_true", help="only print the final verdict")
    args = parser.parse_args(argv)
    try:
        summary = verify_file(args.ledger, args.data)
    except (LedgerIntegrityError, FileNotFoundError) as exc:
        print(f"FAIL: {exc}")
        return 1
    if not args.quiet:
        for i, kind in enumerate(summary["kinds"], 1):
            print(f"  entry {i}: {kind} ✓")
        print(f"  head hash: {summary['head_hash']}")
        if summary.get("data_match"):
            print("  data file sha256 matches data_ingested entry ✓")
    print(f"OK: {summary['entries']} entries, chain intact")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
