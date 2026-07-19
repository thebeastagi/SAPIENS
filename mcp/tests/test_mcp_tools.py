"""Unit tests for the three MCP tools (offline, deterministic)."""

import json
import time

import pytest
from sapiens_ledger_mcp import tools

PUBLISHED_PERIOD_DAYS = 0.8374912
COMMITTED_PERIOD_DAYS = 0.8373346  # nfreq=6000 + refine (demos/ledger-grok/out/results.json)


# ---------------------------------------------------------------- ledger_verify


def test_ledger_verify_pass_on_committed_chain():
    out = tools.ledger_verify()
    assert out["ok"] is True
    assert out["verdict"] == "PASS"
    assert out["entries"] == 6
    assert out["data_match"] is True
    assert len(out["head_hash"]) == 64
    assert out["kinds"] == [
        "data_ingested",
        "hypothesis",
        "analysis",
        "adversarial_challenge",
        "challenge_response",
        "verdict",
    ]


def test_ledger_verify_detects_tamper(tmp_path):
    tampered = tmp_path / "ledger.jsonl"
    lines = tools.LEDGER_PATH.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[2])
    entry["payload"]["period_days"] = 1.234  # modify without re-hashing
    lines[2] = json.dumps(entry)
    tampered.write_text("\n".join(lines) + "\n", encoding="utf-8")
    from ledger_grok.ledger import LedgerIntegrityError
    from ledger_grok.verify import verify_file

    with pytest.raises(LedgerIntegrityError):
        verify_file(tampered)


def test_ledger_verify_missing_file_returns_error(monkeypatch):
    monkeypatch.setattr(tools, "LEDGER_PATH", tools.DEMO_ROOT / "out" / "nope.jsonl")
    out = tools.ledger_verify()
    assert out["ok"] is False
    assert "error" in out


# ----------------------------------------------------------------- ledger_query


def test_ledger_query_all_entries_sanitized_shape():
    out = tools.ledger_query()
    assert out["source"] == "ledger"
    assert out["total"] == 6
    assert out["returned"] == 6
    first = out["entries"][0]
    assert first["kind"] == "data_ingested"
    assert set(first) == {"index", "kind", "actor", "entry_hash", "previous_hash", "payload"}


def test_ledger_query_kind_filter_and_pagination():
    out = tools.ledger_query(kind="hypothesis")
    assert out["total"] == 1
    assert out["entries"][0]["actor"].startswith("grok-mock")
    out = tools.ledger_query(limit=2, offset=4)
    assert out["returned"] == 2
    assert out["entries"][0]["index"] == 4
    out = tools.ledger_query(limit=10_000)  # clamped, not an error
    assert out["returned"] == 6


def test_ledger_query_results_source_and_section():
    out = tools.ledger_query(source="results", section="verdict")
    assert out["section"] == "verdict"
    assert "match" in json.dumps(out["data"]).lower()
    out = tools.ledger_query(source="results", section="no-such-section")
    assert "error" in out
    assert "analysis" in out["available_sections"]


def test_ledger_query_redacts_sensitive_keys():
    redacted = tools._sanitize({"api_key": "x", "nested": {"Authorization": "y"}, "ok": 1})
    assert redacted["api_key"] == tools._REDACTED
    assert redacted["nested"]["Authorization"] == tools._REDACTED
    assert redacted["ok"] == 1
    assert tools._sanitize("z" * 5000).endswith("chars]")


def test_ledger_query_rejects_unknown_source():
    out = tools.ledger_query(source="etc-passwd")
    assert "error" in out


# ------------------------------------------------------------ transit_redetect


def test_transit_redetect_fast_grid_matches_published():
    started = time.time()
    out = tools.transit_redetect(nfreq=600)
    assert time.time() - started < 60  # bounded runtime
    cmp = out["comparison"]
    assert cmp["period_match"] is True
    assert cmp["epoch_match"] is True
    assert cmp["depth_match"] is True
    assert cmp["verdict"].startswith("MATCH")
    assert out["analysis"]["n_transits"] == 40
    assert 100 < out["analysis"]["depth_ppm"] < 250
    assert out["data"]["rows_masked"] == 16  # Kepler-10 c transit mask


def test_transit_redetect_default_grid_reproduces_committed_analysis():
    out = tools.transit_redetect()  # nfreq=6000 + refine, ~25 s
    assert out["analysis"]["period_days"] == COMMITTED_PERIOD_DAYS
    assert out["reproduces_committed_analysis"] is True
    assert abs(out["analysis"]["period_days"] - PUBLISHED_PERIOD_DAYS) <= 5e-4


def test_transit_redetect_is_deterministic():
    a = tools.transit_redetect(nfreq=300, refine=False)
    b = tools.transit_redetect(nfreq=300, refine=False)
    assert a == b


def test_transit_redetect_bounds_nfreq():
    assert "error" in tools.transit_redetect(nfreq=5)
    assert "error" in tools.transit_redetect(nfreq=10**9)
