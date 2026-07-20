"""Seeded-bias fixture suite (Phase 2).

Deterministic, labelled candidates with planted failure modes, used to
calibrate the validation gates (Phase 2) and to score review-panel catch
rates (Phase 3). Every fixture declares its expected gate outcome; the
calibration report is only meaningful because this ground truth exists.

Fixtures are pure evidence data — no adapter behaviour is simulated — so the
suite is stable across Python versions and never touches the ledger.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .models import Candidate, Evidence
from .validation import HoldoutProtocol, synthetic_holdout_protocol

PROTOCOL = synthetic_holdout_protocol()
DOMAIN = "synthetic-fixtures"


class FixtureKind(Enum):
    KNOWN_GOOD = "known-good"  # honest evidence; gates must accept
    OVERFIT = "overfit"  # passes train, fails holdout; L2 must reject
    LEAKAGE = "leakage"  # train/holdout boundary violated; L2 must reject
    DEGENERATE = "degenerate"  # constant scores across seeds; L1 must reject


@dataclass(frozen=True)
class SeededFixture:
    fixture_id: str
    kind: FixtureKind
    candidate: Candidate
    internal: tuple[Evidence, ...]
    replication: tuple[Evidence, ...]
    protocol: HoldoutProtocol
    expect_l1_pass: bool
    expect_l2_pass: bool
    rationale: str


def _evidence(
    fixture: str, stage: str, runs: tuple[tuple[int, str, float, bool], ...]
) -> tuple[Evidence, ...]:
    return tuple(
        Evidence(
            f"{fixture}-{stage}-{index}",
            f"cand-{fixture}",
            stage,
            passed,
            f"fixture-{stage}-v1",
            dataset,
            seed,
            score,
            {"fixture": fixture},
        )
        for index, (seed, dataset, score, passed) in enumerate(runs)
    )


def _candidate(fixture: str, claim: str) -> Candidate:
    return Candidate(f"cand-{fixture}", DOMAIN, claim, source_adapter="fixture-suite")


def fixture_suite() -> tuple[SeededFixture, ...]:
    """The canonical seeded-bias suite. Deterministic; do not mutate."""
    good = SeededFixture(
        "good-1",
        FixtureKind.KNOWN_GOOD,
        _candidate("good-1", "honest signal replicates on holdout"),
        _evidence(
            "good-1",
            "internal",
            ((101, "synthetic-train", 0.91, True), (102, "synthetic-train", 0.89, True)),
        ),
        _evidence(
            "good-1",
            "replication",
            ((201, "synthetic-holdout", 0.88, True), (202, "synthetic-holdout", 0.9, True)),
        ),
        PROTOCOL,
        expect_l1_pass=True,
        expect_l2_pass=True,
        rationale="varying scores, clean split, independent seeds, all runs pass",
    )
    overfit = SeededFixture(
        "overfit-1",
        FixtureKind.OVERFIT,
        _candidate("overfit-1", "signal that only exists in the training split"),
        _evidence(
            "overfit-1",
            "internal",
            ((101, "synthetic-train", 0.95, True), (102, "synthetic-train", 0.93, True)),
        ),
        _evidence(
            "overfit-1",
            "replication",
            ((201, "synthetic-holdout", 0.31, False), (202, "synthetic-holdout", 0.28, False)),
        ),
        PROTOCOL,
        expect_l1_pass=True,
        expect_l2_pass=False,
        rationale="strong on train, collapses on holdout — L2 must catch it",
    )
    leakage = SeededFixture(
        "leakage-1",
        FixtureKind.LEAKAGE,
        _candidate("leakage-1", "'replication' run on the training data itself"),
        _evidence("leakage-1", "internal", ((101, "synthetic-train", 0.92, True),)),
        _evidence("leakage-1", "replication", ((101, "synthetic-train", 0.92, True),)),
        PROTOCOL,
        expect_l1_pass=True,
        expect_l2_pass=False,
        rationale="same dataset and seed on both sides — leakage controls must fire",
    )
    degenerate = SeededFixture(
        "degenerate-1",
        FixtureKind.DEGENERATE,
        _candidate("degenerate-1", "constant score regardless of seed"),
        _evidence(
            "degenerate-1",
            "internal",
            (
                (101, "synthetic-train", 0.5, True),
                (102, "synthetic-train", 0.5, True),
                (103, "synthetic-train", 0.5, True),
            ),
        ),
        _evidence(
            "degenerate-1",
            "replication",
            ((201, "synthetic-holdout", 0.5, True),),
        ),
        PROTOCOL,
        expect_l1_pass=False,
        expect_l2_pass=True,
        rationale="identical score across three independent seeds — no information",
    )
    return (good, overfit, leakage, degenerate)
