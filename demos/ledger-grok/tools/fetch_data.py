#!/usr/bin/env python3
"""One-off data-prep tool: fetch a small public Kepler light curve and write CSV.

This is the only networked step of the demo; the demo itself runs fully
offline on the committed CSV. Streams the FITS to a temp file, parses it with
the stdlib FITS reader (no astropy), writes a two-column CSV with provenance
comments, then deletes the FITS. Total download is capped (default 10 MB).

Usage:
    python tools/fetch_data.py --out data/kepler10_kic11904151_q2_lc.csv
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ledger_grok.fits import read_light_curve

DEFAULT_URI = (
    "mast:Kepler/url/missions/kepler/lightcurves/0119/011904151/"
    "kplr011904151-2009166043257_llc.fits"  # KIC 11904151 (Kepler-10), Quarter 1 (FITS header QUARTER=1), long cadence
)
MAST_DOWNLOAD = "https://mast.stsci.edu/api/v0.1/Download/file?uri="


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=DEFAULT_URI, help="MAST data URI")
    parser.add_argument("--out", required=True, help="output CSV path")
    parser.add_argument("--max-bytes", type=int, default=10_000_000, help="download cap")
    args = parser.parse_args(argv)

    url = MAST_DOWNLOAD + args.uri
    with tempfile.NamedTemporaryFile(suffix=".fits", delete=False) as tmp:
        tmp_path = Path(tmp.name)
        try:
            with urllib.request.urlopen(url, timeout=120) as resp:
                total = 0
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > args.max_bytes:
                        raise RuntimeError(f"download exceeds cap ({args.max_bytes} bytes)")
                    tmp.write(chunk)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    try:
        fits_bytes = tmp_path.read_bytes()
        fits_sha = hashlib.sha256(fits_bytes).hexdigest()
        times, fluxes, meta = read_light_curve(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)  # never keep the FITS around

    retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as fh:
        fh.write("# Kepler-10 (KIC 11904151) long-cadence light curve\n")
        fh.write(f"# source_uri: {args.uri}\n")
        fh.write(f"# source_url: {url}\n")
        fh.write(f"# retrieved_utc: {retrieved}\n")
        fh.write(f"# fits_sha256: {fits_sha}\n")
        fh.write(f"# fits_bytes: {len(fits_bytes)}\n")
        fh.write("# time: BKJD (BJD - 2454833); flux: PDCSAP_FLUX (e-/s), SAP_QUALITY==0 rows only\n")
        fh.write("time_bkjd,flux_e_per_s\n")
        for t, f in zip(times, fluxes, strict=True):
            fh.write(f"{t:.6f},{f:.3f}\n")

    csv_bytes = out.stat().st_size
    print(
        json.dumps(
            {
                "out": str(out),
                "csv_bytes": csv_bytes,
                "csv_sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
                "fits_bytes": len(fits_bytes),
                "fits_sha256": fits_sha,
                **meta,
                "t_start_bkjd": round(min(times), 6),
                "t_end_bkjd": round(max(times), 6),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
