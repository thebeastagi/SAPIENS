#!/usr/bin/env python3
"""Thin wrapper: verify the committed demo ledger (and data hash) with zero args."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ledger_grok.verify import main

if __name__ == "__main__":
    if not any(not a.startswith("-") for a in sys.argv[1:]):  # no positional ledger given
        root = Path(__file__).resolve().parent
        sys.argv[1:1] = [
            str(root / "out" / "ledger.jsonl"),
            "--data",
            str(root / "data" / "kepler10_kic11904151_q1_lc.csv"),
        ]
    raise SystemExit(main())
