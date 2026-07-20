"""Kernel + L3 review panel integration (Phase 3)."""

import json

from sapiens.adapters import SyntheticPhotometryAdapter
from sapiens.budget import ExecutionContext
from sapiens.kernel import DiscoveryKernel
from sapiens.ledger import EvidenceLedger
from sapiens.models import AdapterManifest, Candidate, Evidence, EvidenceLevel
from sapiens.review import PanelOutcome
from sapiens.reviewers import reference_panel
from sapiens.validation import synthetic_holdout_protocol


def ctx():
    return ExecutionContext(max_steps=20, max_seconds=20.0)


def climb(kernel, adapter, candidate, seeds=(40, 41, 42)):
    reached = EvidenceLevel.L0
    for seed in seeds:
        reached = kernel.validate_next(adapter, candidate, seed=seed, context=ctx())
    return reached


def test_panel_approval_path_recorded_end_to_end(tmp_path):
    adapter = SyntheticPhotometryAdapter()
    panel = reference_panel(adapter.manifest.vocabulary, synthetic_holdout_protocol())
    kernel = DiscoveryKernel(EvidenceLedger(tmp_path / "events.jsonl"), panel=panel)
    candidate = adapter.propose(seed=5, limit=1)[0]
    kernel.register(candidate)
    assert climb(kernel, adapter, candidate) == EvidenceLevel.L3
    assert kernel.panel_log[-1].outcome == PanelOutcome.APPROVED
    # The verdict lives in the ledger as review evidence — no side channel.
    panel_records = [
        event
        for event in kernel.ledger.events()
        if event.kind == "evidence" and event.payload["dataset"] == "panel-transcript"
    ]
    assert len(panel_records) == 1
    assert panel_records[0].payload["passed"] is True
    assert panel_records[0].payload["details"]["report"]["outcome"] == "approved"
    assert kernel.ledger.verify()


class PerfectScoreAdapter:
    """Everything exactly 1.0: passes naive gates, trips the devil's advocate."""

    manifest = AdapterManifest("perfect", "1", "perfect-domain", ("signal",))

    def propose(self, *, seed: int, limit: int):
        return (Candidate("cand-perfect", "perfect-domain", "a signal claim"),)

    def validate(self, candidate, *, stage: str, seed: int, context):
        context.checkpoint()
        dataset = "synthetic-train" if stage == "internal" else "synthetic-holdout"
        return (
            Evidence(
                f"ev-{stage}-{seed}",
                candidate.candidate_id,
                stage,
                True,
                f"perfect-{stage}-v1",
                dataset,
                seed,
                1.0,
            ),
        )

    def import_structure(self, structure, *, candidate_id: str):
        return Candidate(candidate_id, "perfect-domain", "claim")


def test_panel_rejection_blocks_l3_and_records_verdict(tmp_path):
    adapter = PerfectScoreAdapter()
    panel = reference_panel(adapter.manifest.vocabulary, synthetic_holdout_protocol())
    kernel = DiscoveryKernel(EvidenceLedger(tmp_path / "events.jsonl"), panel=panel)
    candidate = adapter.propose(seed=1, limit=1)[0]
    kernel.register(candidate)
    assert climb(kernel, adapter, candidate) == EvidenceLevel.L2
    assert kernel.ledger.state("cand-perfect").level == EvidenceLevel.L2
    report = kernel.panel_log[-1]
    assert report.outcome == PanelOutcome.REJECTED
    assert len(report.rounds) == 3  # escalated objection held through the budget
    assert any("implausibly perfect" in o.text for o in report.sustained_blocking)
    panel_records = [
        event
        for event in kernel.ledger.events()
        if event.kind == "evidence" and event.payload["dataset"] == "panel-transcript"
    ]
    assert len(panel_records) == 1
    assert panel_records[0].payload["passed"] is False
    assert kernel.ledger.verify()


def test_repeated_rejection_attempts_do_not_collide(tmp_path):
    adapter = PerfectScoreAdapter()
    panel = reference_panel(adapter.manifest.vocabulary, synthetic_holdout_protocol())
    kernel = DiscoveryKernel(EvidenceLedger(tmp_path / "events.jsonl"), panel=panel)
    candidate = adapter.propose(seed=1, limit=1)[0]
    kernel.register(candidate)
    assert kernel.validate_next(adapter, candidate, seed=40, context=ctx()) == EvidenceLevel.L1
    assert kernel.validate_next(adapter, candidate, seed=41, context=ctx()) == EvidenceLevel.L2
    assert kernel.validate_next(adapter, candidate, seed=42, context=ctx()) == EvidenceLevel.L2
    # A second L3 attempt with a fresh seed must not hit duplicate evidence ids.
    assert kernel.validate_next(adapter, candidate, seed=43, context=ctx()) == EvidenceLevel.L2
    assert kernel.ledger.verify()
    reports = [
        event
        for event in kernel.ledger.events()
        if event.kind == "evidence" and event.payload["dataset"] == "panel-transcript"
    ]
    assert len(reports) == 2


def test_kernel_without_panel_unchanged(tmp_path):
    adapter = SyntheticPhotometryAdapter()
    kernel = DiscoveryKernel(EvidenceLedger(tmp_path / "events.jsonl"))
    candidate = adapter.propose(seed=5, limit=1)[0]
    kernel.register(candidate)
    assert climb(kernel, adapter, candidate) == EvidenceLevel.L3
    assert kernel.panel_log == []


def test_panel_report_blob_is_json_safe(tmp_path):
    adapter = PerfectScoreAdapter()
    panel = reference_panel(adapter.manifest.vocabulary, synthetic_holdout_protocol())
    kernel = DiscoveryKernel(EvidenceLedger(tmp_path / "events.jsonl"), panel=panel)
    candidate = adapter.propose(seed=1, limit=1)[0]
    kernel.register(candidate)
    climb(kernel, adapter, candidate)
    json.dumps(kernel.panel_log[-1].to_dict())
