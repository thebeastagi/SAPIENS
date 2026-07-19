"""Orchestrator: run the LEDGER demo end to end and write artifacts.

Pipeline order (each step is appended to the hash-chained ledger):
  data_ingested -> hypothesis (Grok adapter) -> analysis (BLS) ->
  adversarial_challenge (Grok adapter) -> challenge_response -> verdict.

The verdict compares the measured signal against the published Kepler-10 b
ephemeris. This is a *validation* demo: it re-derives a published result.
No discovery is claimed anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from .grok_adapter import get_adapter
from .ledger import Ledger, load_entries, verify_entries
from .pipeline import bls, detrend, fold_measure, harmonic_powers, load_csv

BKJD0 = 2454833.0
PUBLISHED = {
    "name": "Kepler-10 b",
    "source": (
        "NASA Exoplanet Archive Planetary Systems (ps) table via TAP "
        "(pl_orbper/pl_tranmid/pl_trandep/pl_trandur), retrieved 2026-07-19"
    ),
    "period_days": 0.8374912,
    "epoch_bjd": 2454964.574756,
    "depth_ppm": 191.0,
    "duration_hours": 1.8076,
}
TOL_PERIOD_DAYS = 5e-4
TOL_EPOCH_MINUTES = 30.0
DEPTH_RATIO_RANGE = (0.4, 2.5)

DATA_FILE = "kepler10_kic11904151_q1_lc.csv"

# The Q1 segment contains ONE transit of Kepler-10 c (P = 45.3 d, outside the
# 0.5-10 d search window): a ~450 ppm, ~5.5 h depression at BKJD ~138.6-138.8.
# It belongs to a different (also already known) planet, so it is masked out of
# the single-period search and disclosed here + in the ledger, not hidden.
MASK_EVENTS = [
    {
        "name": "Kepler-10 c single transit (known planet, P=45.3 d, out of search scope)",
        "t_start_bkjd": 138.54,
        "t_end_bkjd": 138.86,
    }
]


def run(
    data_path: str | Path,
    out_dir: str | Path,
    adapter_name: str = "mock",
    nfreq: int = 6000,
    pmin: float = 0.5,
    pmax: float = 10.0,
    refine: bool = True,
) -> dict:
    started = time.time()
    data_path = Path(data_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = data_path.read_bytes()
    data_sha = hashlib.sha256(raw).hexdigest()
    times_all, fluxes_all = load_csv(data_path)
    keep = [
        not any(ev["t_start_bkjd"] <= t <= ev["t_end_bkjd"] for ev in MASK_EVENTS)
        for t in times_all
    ]
    times = [t for t, k in zip(times_all, keep, strict=True) if k]
    fluxes = [f for f, k in zip(fluxes_all, keep, strict=True) if k]
    span = max(times_all) - min(times_all)

    for stale in ("ledger.jsonl", "results.json"):  # artifacts are regenerated each run
        (out_dir / stale).unlink(missing_ok=True)
    ledger = Ledger(out_dir / "ledger.jsonl")

    ledger.append(
        "sapiens-demo-pipeline",
        "data_ingested",
        {
            "file": data_path.name,
            "sha256": data_sha,
            "bytes": len(raw),
            "rows": len(times_all),
            "rows_masked": len(times_all) - len(times),
            "masked_events": MASK_EVENTS,
            "t_start_bkjd": round(min(times_all), 6),
            "t_end_bkjd": round(max(times_all), 6),
            "span_days": round(span, 3),
            "source": (
                "NASA Kepler long-cadence light curve, KIC 11904151 (Kepler-10), "
                "Quarter 1 (FITS header QUARTER=1), via MAST — provenance in data/README.md"
            ),
        },
    )

    adapter = get_adapter(adapter_name, data_sha)
    context = {
        "target": "Kepler-10 (KIC 11904151)",
        "rows": len(times),
        "span_days": round(span, 2),
        "cadence": "Kepler long cadence (~29.4 min)",
        "flux": "PDCSAP, median-normalised",
    }
    hypothesis = adapter.generate_hypothesis(context)
    ledger.append(adapter.name, "hypothesis", hypothesis)

    y = detrend(times, fluxes)
    search = bls(times, y, pmin=pmin, pmax=pmax, nfreq=nfreq, refine=refine)
    meas = fold_measure(times, y, search["period_days"], search["phase_center"], search["q"])
    analysis = {
        "method": (
            "running-median detrend + box-least-squares grid search "
            "(simplified Kovacs et al. 2002), pure stdlib"
        ),
        "grid": search["grid"],
        "period_days": round(search["period_days"], 8),
        "bls_power": search["power"],
        "bls_power_scaled_1e12": round(search["power"] * 1e12, 3),
        "duration_fraction_q": round(search["q"], 5),
        "phase_center": round(search["phase_center"], 6),
        "depth_ppm": round(meas["depth_ppm"], 2),
        "snr": round(meas["snr"], 2),
        "n_transits": meas["n_transits"],
        "epoch_bkjd": round(meas["epoch_bkjd"], 6),
        "std_out_ppm": round(meas["std_out_ppm"], 2),
    }
    ledger.append("sapiens-demo-pipeline", "analysis", analysis)

    challenge = adapter.adversarial_challenge(analysis)
    ledger.append(adapter.name, "adversarial_challenge", challenge)

    harmonics = harmonic_powers(times, y, search["period_days"])
    oe, sec = meas["odd_even"], meas["secondary"]
    response = {
        "harmonic_confusion": {
            "powers": {
                k: {
                    "period_days": round(v["period_days"], 8),
                    "power_scaled_1e12": round(v["power"] * 1e12, 3),
                }
                for k, v in harmonics.items()
            },
            "interpretation": (
                "power at 2P is expected to stay high (transits coincide modulo 2P); "
                "the informative comparison is P vs P/2, where transits split into two boxes"
            ),
            "pass": harmonics["fundamental"]["power"] >= harmonics["half"]["power"],
        },
        "odd_even_depth": {
            "depth_even_ppm": round(oe["depth_even_ppm"], 2),
            "depth_odd_ppm": round(oe["depth_odd_ppm"], 2),
            "delta_sigma": round(oe["delta_sigma"], 3),
            "pass": abs(oe["delta_sigma"]) < 3.0,
        },
        "secondary_eclipse": {
            "depth_ppm": round(sec["depth_ppm"], 2),
            "sigma": round(sec["sigma"], 3),
            "pass": abs(sec["sigma"]) < 3.0,
        },
    }
    ledger.append("sapiens-demo-pipeline", "challenge_response", response)

    t0_pub_bkjd = PUBLISHED["epoch_bjd"] - BKJD0
    k = round((t0_pub_bkjd - meas["epoch_bkjd"]) / search["period_days"])
    epoch_delta_min = abs(t0_pub_bkjd - (meas["epoch_bkjd"] + k * search["period_days"])) * 1440.0
    period_delta = abs(search["period_days"] - PUBLISHED["period_days"])
    depth_ratio = meas["depth_ppm"] / PUBLISHED["depth_ppm"]
    checks = {
        "period_match": period_delta <= TOL_PERIOD_DAYS,
        "epoch_match": epoch_delta_min <= TOL_EPOCH_MINUTES,
        "depth_consistent": DEPTH_RATIO_RANGE[0] <= depth_ratio <= DEPTH_RATIO_RANGE[1],
        "adversarial_clean": all(v["pass"] for v in response.values()),
    }
    verdict = {
        "claim": "validation — re-derivation of a published result; NOT a new discovery",
        "target": PUBLISHED["name"],
        "match": all(checks.values()),
        "checks": checks,
        "measured": {
            "period_days": round(search["period_days"], 8),
            "epoch_bkjd": round(meas["epoch_bkjd"], 6),
            "depth_ppm": round(meas["depth_ppm"], 2),
            "snr": round(meas["snr"], 2),
            "n_transits": meas["n_transits"],
        },
        "published": PUBLISHED,
        "deltas": {
            "period_days": period_delta,
            "epoch_minutes_vs_published_ephemeris": round(epoch_delta_min, 2),
            "depth_ratio": round(depth_ratio, 3),
        },
    }
    ledger.append("sapiens-demo-pipeline", "verdict", verdict)

    entries = load_entries(out_dir / "ledger.jsonl")
    verify_entries(entries)  # self-check before publishing results

    results = {
        "demo": "SAPIENS x Grok LEDGER demo — Kepler-10 b rediscovery (validation, not a discovery)",
        "generated_utc": entries[-1].ts,
        "adapter_mode": adapter_name,
        "adapter": adapter.name,
        "data": {
            "file": data_path.name,
            "sha256": data_sha,
            "rows": len(times),
            "span_days": round(span, 3),
            "t_start_bkjd": round(min(times), 6),
            "t_end_bkjd": round(max(times), 6),
        },
        "hypothesis": hypothesis,
        "analysis": analysis,
        "challenge": challenge,
        "challenge_response": response,
        "verdict": verdict,
        "ledger": {
            "file": "ledger.jsonl",
            "entries": len(entries),
            "head_hash": entries[-1].entry_hash,
            "sha256": hashlib.sha256((out_dir / "ledger.jsonl").read_bytes()).hexdigest(),
        },
        "runtime_seconds": round(time.time() - started, 2),
        "reproduce": (
            "python demos/ledger-grok/run_demo.py && python demos/ledger-grok/verify_ledger.py"
        ),
    }
    (out_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return results


def main(argv: list[str] | None = None) -> int:
    demo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Run the SAPIENS x Grok LEDGER demo.")
    parser.add_argument("--data", default=str(demo_root / "data" / DATA_FILE))
    parser.add_argument("--out", default=str(demo_root / "out"))
    parser.add_argument("--adapter", choices=["mock", "real"], default="mock")
    parser.add_argument("--nfreq", type=int, default=6000, help="coarse frequency-grid size")
    parser.add_argument("--no-refine", action="store_true", help="skip the fine refine pass")
    parser.add_argument(
        "--quick", action="store_true", help="small grid (nfreq=800, no refine) for a fast smoke run"
    )
    args = parser.parse_args(argv)
    results = run(
        args.data,
        args.out,
        adapter_name=args.adapter,
        nfreq=800 if args.quick else args.nfreq,
        refine=not (args.quick or args.no_refine),
    )
    v = results["verdict"]
    print(f"adapter        : {results['adapter']}")
    print(f"period         : {v['measured']['period_days']} d (published {v['published']['period_days']} d)")
    print(f"depth          : {v['measured']['depth_ppm']} ppm (published {v['published']['depth_ppm']} ppm)")
    print(f"SNR / transits : {v['measured']['snr']} / {v['measured']['n_transits']}")
    print(f"epoch delta    : {v['deltas']['epoch_minutes_vs_published_ephemeris']} min vs published ephemeris")
    print(f"verdict match  : {v['match']}  ({v['claim']})")
    print(f"ledger         : {Path(args.out) / 'ledger.jsonl'} ({results['ledger']['entries']} entries)")
    print(f"head hash      : {results['ledger']['head_hash']}")
    return 0 if v["match"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
