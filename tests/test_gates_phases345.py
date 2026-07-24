"""Phase 3 (blind harness), Phase 4 (human-gate dossier), Phase 5 (criteria),
plus the clean-room invariant for the gates subpackage."""

import ast
from pathlib import Path

from sapiens.gates.blind import (
    Verdict,
    blind_run,
    grade,
    seal,
    strip_to_blind,
)
from sapiens.gates.corpus import decoys, full_corpus, historical_positives
from sapiens.gates.criteria import run_success_criteria
from sapiens.gates.dossier import (
    OverrideLog,
    autonomous_claim_eligible,
    build_dossier,
)
from sapiens.gates.pipeline import evaluate_family
from sapiens.gates.thresholds import Tier

ROOT = Path(__file__).resolve().parents[1]


# --- Phase 3: blind re-run harness --------------------------------------- #
def test_blind_strip_removes_key_fields():
    item = historical_positives()[0]
    blind = strip_to_blind(item)
    # The stripped object is just the model inputs — no ground_truth/verdict/how_*.
    assert not hasattr(blind, "ground_truth")
    assert not hasattr(blind, "expected_verdict")
    assert not hasattr(blind, "how_old_gate_would_kill")


def test_blind_custody_commitment_and_grade():
    corpus = full_corpus()
    sealed = seal(corpus, seed=3)
    assert sealed.key.verify_commitment()
    verdicts = blind_run(sealed, run_id="blind-test")
    report = grade(verdicts, sealed.key)
    # Real null layer, answers not inline: kill/recovery targets met, low abstention.
    assert report.kill_rate >= 0.8
    assert report.recovery_rate >= 0.8
    assert report.abstention_rate < 0.10
    assert report.leaks == ()


def test_blind_scorer_sees_no_labels():
    # The blind runner only receives GateInputs; assert none carry a label attr.
    sealed = seal(full_corpus(), seed=1)
    for gi in sealed.blind_inputs:
        assert not hasattr(gi, "label")


def test_tampered_custody_key_is_rejected():
    sealed = seal(decoys(), seed=1)
    bad = sealed.key.__class__(labels={"x": "positive"}, commitment="deadbeef")
    verdicts = blind_run(sealed)
    try:
        grade(verdicts, bad)
    except ValueError:
        return
    raise AssertionError("tampered custody key should have been rejected")


# --- Phase 4: human-in-loop gate ----------------------------------------- #
def test_dossier_forces_disconfirming_explanation():
    fam = evaluate_family([it.inputs for it in historical_positives()], run_id="d")
    for o in fam.outcomes:
        d = build_dossier(o)
        assert d.strongest_disconfirming_explanation  # never empty
        assert "null_used" in d.to_dict()


def test_only_confirm_tier_is_claim_eligible():
    fam = evaluate_family([it.inputs for it in full_corpus()], run_id="d")
    for o in fam.outcomes:
        eligible = autonomous_claim_eligible(o)
        assert eligible == (o.tier == Tier.CONFIRM)
        # Nothing below CONFIRM is ever autonomously claimable.
        if o.tier in (Tier.ENTRY, Tier.UNCALIBRATED):
            assert not eligible


def test_override_log_feeds_labeled_data():
    fam = evaluate_family([it.inputs for it in historical_positives()], run_id="d")
    log = OverrideLog()
    log.record(fam.outcomes[0], human_verdict="pursue", rationale="looks real",
               timestamp="2026-07-24T00:00:00Z")
    log.record(fam.outcomes[1], human_verdict="reject", rationale="artifact",
               timestamp="2026-07-24T00:01:00Z")
    labels = log.as_training_labels()
    assert len(labels) == 2
    assert all(v in ("pursue", "reject", "defer") for _, v in labels)
    assert 0.0 <= log.disagreement_rate() <= 1.0


# --- Phase 5: success-criteria suite ------------------------------------- #
def test_success_criteria_all_pass():
    suite = run_success_criteria()
    failing = [c.name for c in suite.criteria if not c.passed]
    assert not failing, f"failing criteria: {failing}"
    assert suite.all_passed
    assert suite.to_dict()["scientific_discoveries_claimed"] == 0


def test_verdict_vocabulary_is_total():
    sealed = seal(full_corpus(), seed=2)
    verdicts = blind_run(sealed)
    assert all(isinstance(v, Verdict) for v in verdicts.values())


# --- clean-room invariant for the gates subpackage ----------------------- #
def test_gates_subpackage_is_clean_room():
    forbidden_imports = ("sapiens.adapters",)
    forbidden_names = ("astra", "geodisc", "biodisc", "slate")
    for path in (ROOT / "src" / "sapiens" / "gates").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith(forbidden_imports), path
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(forbidden_imports), path
        # No copied ASTRA-family identifiers leaked into code (docstrings ok).
        lowered = "\n".join(
            line for line in path.read_text().splitlines()
            if not line.strip().startswith("#")
        ).lower()
        for name in forbidden_names:
            assert f"import {name}" not in lowered, (path, name)
