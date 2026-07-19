"""Anchors the committed demo run: real data file + committed ledger.

These tests make the published artifacts self-checking in CI: the CSV must
be the real Kepler-10 Q1 segment, and the committed ledger must verify,
reference that exact CSV by sha256, and carry an honest validation verdict.
"""

import json
from pathlib import Path

import pytest

from ledger_grok.ledger import load_entries, verify_entries
from ledger_grok.pipeline import load_csv
from ledger_grok.verify import verify_file

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "kepler10_kic11904151_q1_lc.csv"
LEDGER = ROOT / "out" / "ledger.jsonl"
RESULTS = ROOT / "out" / "results.json"


def test_committed_csv_is_the_real_segment():
    times, fluxes = load_csv(DATA)
    assert len(times) > 1400  # Q1 long cadence after quality cuts
    assert 30.0 < max(times) - min(times) < 40.0  # ~33.5-day quarter
    assert min(times) == pytest.approx(131.512, abs=0.01)
    med = sorted(fluxes)[len(fluxes) // 2]
    assert 5.0e5 < med < 6.0e5  # Kepler-10 PDCSAP flux level (e-/s)


def test_committed_ledger_verifies_and_matches_data():
    summary = verify_file(LEDGER, DATA)
    assert summary["entries"] == 6
    assert summary["kinds"] == [
        "data_ingested",
        "hypothesis",
        "analysis",
        "adversarial_challenge",
        "challenge_response",
        "verdict",
    ]


def test_verdict_is_honest_validation():
    entries = load_entries(LEDGER)
    verdict = entries[-1].payload
    assert verdict["target"] == "Kepler-10 b"
    assert verdict["match"] is True
    assert "NOT a new discovery" in verdict["claim"]
    assert all(verdict["checks"].values())
    # measured period consistent with the published one within demo tolerance
    assert abs(verdict["measured"]["period_days"] - 0.8374912) <= 5e-4


def test_results_json_is_consistent_with_ledger():
    results = json.loads(RESULTS.read_text())
    entries = load_entries(LEDGER)
    assert results["ledger"]["head_hash"] == entries[-1].entry_hash
    assert results["adapter_mode"] == "mock"
    assert results["verdict"]["match"] is True


PROBE = ROOT / "out" / "grok-live-probe.json"


def test_live_probe_artifact_is_sanitized():
    """The bounded live proof must record status/usage/reply only — no secrets."""
    if not PROBE.exists():
        pytest.skip("no live probe artifact (mock-only checkout)")
    probe = json.loads(PROBE.read_text())
    assert probe["http_status"] == 200
    assert probe["usage"]["total_tokens"] > 0
    assert probe["reply_text"]
    blob = PROBE.read_text().lower()
    for marker in ("bearer ", "authorization", "api_key", "xai-"):
        assert marker not in blob
