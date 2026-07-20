"""Calibration reports (Phase 2): gate performance against ground truth.

A calibration report runs the validation gates over the seeded-bias fixture
suite and records, per fixture, whether each gate behaved as the fixture's
label demands. The resulting rates — known-bad catch rate, known-good false
-reject rate — are the *only* legitimate basis for confidence aggregation
(see ``sapiens.confidence``). A report also carries its sample counts so a
thin report cannot masquerade as a strong one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .fixtures import FixtureKind, SeededFixture
from .validation import check_internal_consistency, check_replication

KNOWN_BAD_KINDS = (FixtureKind.OVERFIT, FixtureKind.LEAKAGE, FixtureKind.DEGENERATE)


@dataclass(frozen=True)
class FixtureOutcome:
    fixture_id: str
    kind: str
    l1_passed: bool
    l2_passed: bool
    l1_reasons: tuple[str, ...]
    l2_reasons: tuple[str, ...]


@dataclass(frozen=True)
class CalibrationReport:
    """Immutable gate-performance record over a labelled fixture suite."""

    report_id: str
    outcomes: tuple[FixtureOutcome, ...]
    known_good_total: int
    known_good_accepted: int
    known_bad_total: int
    known_bad_caught: int

    @property
    def catch_rate(self) -> float:
        """Fraction of known-bad fixtures at least one gate correctly rejected."""
        return self.known_bad_caught / self.known_bad_total if self.known_bad_total else 0.0

    @property
    def false_reject_rate(self) -> float:
        """Fraction of known-good fixtures some gate wrongly rejected."""
        if not self.known_good_total:
            return 1.0  # no evidence of reliability: assume the worst, honestly
        return 1.0 - self.known_good_accepted / self.known_good_total

    def meets_minimum(self, *, min_known_bad: int, min_known_good: int) -> bool:
        return self.known_bad_total >= min_known_bad and self.known_good_total >= min_known_good

    def to_dict(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "known_good_total": self.known_good_total,
            "known_good_accepted": self.known_good_accepted,
            "known_bad_total": self.known_bad_total,
            "known_bad_caught": self.known_bad_caught,
            "catch_rate": self.catch_rate,
            "false_reject_rate": self.false_reject_rate,
            "outcomes": [
                {
                    "fixture_id": o.fixture_id,
                    "kind": o.kind,
                    "l1_passed": o.l1_passed,
                    "l2_passed": o.l2_passed,
                }
                for o in self.outcomes
            ],
        }


def _report_id(outcomes: tuple[FixtureOutcome, ...]) -> str:
    canonical = json.dumps(
        [(o.fixture_id, o.l1_passed, o.l2_passed) for o in outcomes],
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def run_calibration(fixtures: tuple[SeededFixture, ...]) -> CalibrationReport:
    """Evaluate both gates on every fixture and tally against labels."""
    outcomes: list[FixtureOutcome] = []
    good_total = good_accepted = bad_total = bad_caught = 0
    for fixture in fixtures:
        l1 = check_internal_consistency(fixture.internal)
        l2 = check_replication(fixture.internal, fixture.replication, fixture.protocol)
        if l1.passed != fixture.expect_l1_pass or l2.passed != fixture.expect_l2_pass:
            raise AssertionError(
                f"fixture {fixture.fixture_id!r} label disagrees with gates: "
                f"expected L1={fixture.expect_l1_pass} L2={fixture.expect_l2_pass}, "
                f"got L1={l1.passed} L2={l2.passed} — fix the fixture or the gate"
            )
        outcomes.append(
            FixtureOutcome(
                fixture.fixture_id,
                fixture.kind.value,
                l1.passed,
                l2.passed,
                l1.reasons,
                l2.reasons,
            )
        )
        if fixture.kind == FixtureKind.KNOWN_GOOD:
            good_total += 1
            if l1.passed and l2.passed:
                good_accepted += 1
        elif fixture.kind in KNOWN_BAD_KINDS:
            bad_total += 1
            if not (l1.passed and l2.passed):
                bad_caught += 1
    result = tuple(outcomes)
    return CalibrationReport(
        _report_id(result),
        result,
        good_total,
        good_accepted,
        bad_total,
        bad_caught,
    )
