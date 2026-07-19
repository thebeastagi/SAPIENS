"""Read-only tool implementations for the SAPIENS LEDGER MCP server.

Every tool operates exclusively on files committed inside this repository
(demos/ledger-grok/). No tool accepts a filesystem path, touches the
network, reads environment variables, or writes anything.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_ROOT = REPO_ROOT / "demos" / "ledger-grok"
LEDGER_PATH = DEMO_ROOT / "out" / "ledger.jsonl"
RESULTS_PATH = DEMO_ROOT / "out" / "results.json"
DATA_PATH = DEMO_ROOT / "data" / "kepler10_kic11904151_q1_lc.csv"

# Demo package is importable in-place; no installation required.
sys.path.insert(0, str(DEMO_ROOT / "src"))

from ledger_grok.pipeline import bls, detrend, fold_measure, load_csv  # noqa: E402
from ledger_grok.run import BKJD0, MASK_EVENTS, PUBLISHED, TOL_PERIOD_DAYS  # noqa: E402
from ledger_grok.verify import verify_file  # noqa: E402

# Published epoch is BJD; pipeline epochs are BKJD (= BJD - 2454833.0).
_TOL_EPOCH_DAYS = 30.0 / (24.0 * 60.0)  # TOL_EPOCH_MINUTES = 30.0
_DEPTH_RATIO_RANGE = (0.4, 2.5)

_NFREQ_MIN, _NFREQ_MAX, _NFREQ_DEFAULT = 100, 6000, 6000
_MAX_LIMIT = 100
_MAX_STR = 1000

# Defence in depth: none of the committed artifacts contain credentials
# (CI checks this), but the query tool redacts defensively anyway.
_SENSITIVE_MARKERS = ("token", "secret", "password", "api_key", "apikey", "authorization")
_REDACTED = "***redacted***"


def _sanitize(value: Any, *, _depth: int = 0) -> Any:
    """Recursively redact sensitive-looking keys and bound string sizes."""
    if _depth > 12:
        return "***max-depth***"
    if isinstance(value, dict):
        out = {}
        for key, val in value.items():
            if any(marker in str(key).lower() for marker in _SENSITIVE_MARKERS):
                out[key] = _REDACTED
            else:
                out[key] = _sanitize(val, _depth=_depth + 1)
        return out
    if isinstance(value, list):
        return [_sanitize(v, _depth=_depth + 1) for v in value[:_MAX_LIMIT]]
    if isinstance(value, str) and len(value) > _MAX_STR:
        return value[:_MAX_STR] + f"…[truncated {len(value) - _MAX_STR} chars]"
    return value


def ledger_verify() -> dict:
    """Verify the committed ledger hash chain and the data-file sha256."""
    try:
        summary = verify_file(LEDGER_PATH, DATA_PATH)
    except Exception as exc:  # LedgerIntegrityError / FileNotFoundError / json errors
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "ledger": str(LEDGER_PATH.relative_to(REPO_ROOT)),
        }
    return {
        "ok": True,
        "verdict": "PASS",
        "entries": summary["entries"],
        "kinds": summary["kinds"],
        "head_hash": summary["head_hash"],
        "genesis_link": summary["genesis_link"],
        "data_match": summary.get("data_match", False),
        "ledger": str(LEDGER_PATH.relative_to(REPO_ROOT)),
        "data": str(DATA_PATH.relative_to(REPO_ROOT)),
    }


def ledger_query(
    source: str = "ledger",
    kind: str | None = None,
    limit: int = 50,
    offset: int = 0,
    section: str | None = None,
) -> dict:
    """Return sanitized ledger entries (or results.json fields).

    source: "ledger" for out/ledger.jsonl entries, "results" for out/results.json.
    kind:   optional entry-kind filter (ledger source only).
    section: optional top-level key of results.json (results source only).
    """
    limit = max(1, min(int(limit), _MAX_LIMIT))
    offset = max(0, int(offset))
    if source == "ledger":
        entries: list[dict] = []
        with LEDGER_PATH.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        if kind is not None:
            entries = [e for e in entries if e.get("kind") == kind]
        total = len(entries)
        window = entries[offset : offset + limit]
        return {
            "source": "ledger",
            "path": str(LEDGER_PATH.relative_to(REPO_ROOT)),
            "total": total,
            "offset": offset,
            "returned": len(window),
            "entries": [
                {
                    "index": offset + i,
                    "kind": e.get("kind"),
                    "actor": e.get("actor"),
                    "entry_hash": e.get("entry_hash"),
                    "previous_hash": e.get("previous_hash"),
                    "payload": _sanitize(e.get("payload", {})),
                }
                for i, e in enumerate(window)
            ],
        }
    if source == "results":
        results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        if section is not None:
            if section not in results:
                return {
                    "source": "results",
                    "error": f"unknown section {section!r}",
                    "available_sections": sorted(results.keys()),
                }
            return {
                "source": "results",
                "path": str(RESULTS_PATH.relative_to(REPO_ROOT)),
                "section": section,
                "data": _sanitize(results[section]),
            }
        return {
            "source": "results",
            "path": str(RESULTS_PATH.relative_to(REPO_ROOT)),
            "sections": sorted(results.keys()),
            "data": _sanitize(results),
        }
    return {"error": f"unknown source {source!r}", "valid_sources": ["ledger", "results"]}


def _masked_light_curve() -> tuple[list[float], list[float], str, int]:
    raw = DATA_PATH.read_bytes()
    data_sha = hashlib.sha256(raw).hexdigest()
    times_all, fluxes_all = load_csv(DATA_PATH)
    keep = [
        not any(ev["t_start_bkjd"] <= t <= ev["t_end_bkjd"] for ev in MASK_EVENTS)
        for t in times_all
    ]
    times = [t for t, k in zip(times_all, keep, strict=True) if k]
    fluxes = [f for f, k in zip(fluxes_all, keep, strict=True) if k]
    return times, fluxes, data_sha, len(times_all) - len(times)


def transit_redetect(nfreq: int = _NFREQ_DEFAULT, refine: bool = True) -> dict:
    """Re-run the bounded Kepler-10 b detection on the committed sample CSV.

    Deterministic and offline: identical inputs always produce identical
    outputs. nfreq is bounded to [100, 6000]; the default (6000) reproduces
    the committed analysis exactly.
    """
    nfreq = int(nfreq)
    if not (_NFREQ_MIN <= nfreq <= _NFREQ_MAX):
        return {"error": f"nfreq must be within [{_NFREQ_MIN}, {_NFREQ_MAX}], got {nfreq}"}
    times, fluxes, data_sha, rows_masked = _masked_light_curve()
    y = detrend(times, fluxes)
    search = bls(times, y, pmin=0.5, pmax=10.0, nfreq=nfreq, refine=bool(refine))
    meas = fold_measure(times, y, search["period_days"], search["phase_center"], search["q"])
    analysis = {
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
    delta_p = abs(search["period_days"] - PUBLISHED["period_days"])
    delta_epoch_days = abs(meas["epoch_bkjd"] - (PUBLISHED["epoch_bjd"] - BKJD0))
    depth_ratio = meas["depth_ppm"] / PUBLISHED["depth_ppm"]
    comparison = {
        "published": {
            "name": PUBLISHED["name"],
            "period_days": PUBLISHED["period_days"],
            "epoch_bjd": PUBLISHED["epoch_bjd"],
            "depth_ppm": PUBLISHED["depth_ppm"],
        },
        "delta_period_days": round(delta_p, 8),
        "delta_epoch_minutes": round(delta_epoch_days * 24 * 60, 2),
        "depth_ratio": round(depth_ratio, 3),
        "period_match": delta_p <= TOL_PERIOD_DAYS,
        "epoch_match": delta_epoch_days <= _TOL_EPOCH_DAYS,
        "depth_match": _DEPTH_RATIO_RANGE[0] <= depth_ratio <= _DEPTH_RATIO_RANGE[1],
    }
    comparison["verdict"] = (
        "MATCH (validation, not a discovery)"
        if (comparison["period_match"] and comparison["epoch_match"] and comparison["depth_match"])
        else "MISMATCH"
    )
    committed = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))["analysis"]
    reproduces = (
        nfreq == _NFREQ_DEFAULT
        and bool(refine)
        and analysis["period_days"] == committed["period_days"]
        and analysis["depth_ppm"] == committed["depth_ppm"]
        and analysis["n_transits"] == committed["n_transits"]
    )
    return {
        "data": {
            "file": DATA_PATH.name,
            "sha256": data_sha,
            "rows_used": len(times),
            "rows_masked": rows_masked,
            "masked_events": [ev["name"] for ev in MASK_EVENTS],
        },
        "analysis": analysis,
        "comparison": comparison,
        "reproduces_committed_analysis": reproduces,
        "note": "Validation re-derivation of a published result; no discovery is claimed.",
    }


# JSON Schema advertised over tools/list. Keep in sync with the signatures.
TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "ledger_verify",
        "description": (
            "Verify the committed SAPIENS LEDGER-demo hash chain "
            "(demos/ledger-grok/out/ledger.jsonl) and the sha256 of the data file "
            "recorded in its data_ingested entry. Returns pass/fail, entry count, "
            "entry kinds, and the chain head hash. Read-only and offline."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "ledger_query",
        "description": (
            "Return sanitized entries from the committed ledger "
            "(demos/ledger-grok/out/ledger.jsonl) or fields from "
            "demos/ledger-grok/out/results.json. Sensitive-looking keys are "
            "redacted and long strings truncated. Read-only and offline."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "enum": ["ledger", "results"],
                    "description": "'ledger' (default) or 'results'.",
                },
                "kind": {
                    "type": "string",
                    "description": "Optional ledger entry-kind filter (ledger source only).",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": _MAX_LIMIT,
                    "description": "Max entries to return (default 50, max 100).",
                },
                "offset": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Entry offset for pagination (default 0).",
                },
                "section": {
                    "type": "string",
                    "description": "Optional top-level key of results.json (results source only).",
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "transit_redetect",
        "description": (
            "Re-run the bounded Kepler-10 b transit detection on the committed "
            "sample light curve (demos/ledger-grok/data/…q1_lc.csv): running-median "
            "detrend + box-least-squares, pure stdlib, deterministic and offline. "
            "Default grid (nfreq=6000 + refine) reproduces the committed analysis "
            "exactly. Runtime is bounded (~25 s at the default grid)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "nfreq": {
                    "type": "integer",
                    "minimum": _NFREQ_MIN,
                    "maximum": _NFREQ_MAX,
                    "description": "BLS grid size, 100-6000 (default 6000).",
                },
                "refine": {
                    "type": "boolean",
                    "description": "Fine refine pass around the grid peak (default true).",
                },
            },
            "additionalProperties": False,
        },
    },
]

TOOL_FUNCTIONS = {
    "ledger_verify": ledger_verify,
    "ledger_query": ledger_query,
    "transit_redetect": transit_redetect,
}
