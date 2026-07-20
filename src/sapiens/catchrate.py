"""Catch-rate scoring for review panels (Phase 3).

Runs a panel over the labelled seeded-bias fixture suite and reports, per
role and for the panel as a whole, how often known-bad candidates draw
substantive (MAJOR/BLOCKING) objections and known-good candidates are
approved. Rates are exact for the fixtures included — they are *not*
estimates of performance on unseeded candidates, and the report says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from .calibration import KNOWN_BAD_KINDS
from .fixtures import FixtureKind, SeededFixture
from .review import PanelOutcome, ReviewPanel, Severity

CAVEAT = (
    "Catch rates are exact for the seeded fixture suite only; they do not "
    "estimate performance on unseeded candidates."
)


@dataclass(frozen=True)
class RoleCatchStats:
    role: str
    bad_fixtures_objected: int
    bad_fixtures_total: int

    @property
    def rate(self) -> float:
        return (
            self.bad_fixtures_objected / self.bad_fixtures_total
            if self.bad_fixtures_total
            else 0.0
        )


@dataclass(frozen=True)
class CatchRateReport:
    per_role: tuple[RoleCatchStats, ...]
    panel_catches: int
    known_bad_total: int
    known_good_total: int
    known_good_approved: int
    caveat: str = CAVEAT

    @property
    def panel_catch_rate(self) -> float:
        return self.panel_catches / self.known_bad_total if self.known_bad_total else 0.0

    @property
    def false_reject_rate(self) -> float:
        if not self.known_good_total:
            return 1.0
        return 1.0 - self.known_good_approved / self.known_good_total

    def to_dict(self) -> dict[str, object]:
        return {
            "per_role": {
                stats.role: {
                    "bad_fixtures_objected": stats.bad_fixtures_objected,
                    "bad_fixtures_total": stats.bad_fixtures_total,
                    "rate": stats.rate,
                }
                for stats in self.per_role
            },
            "panel_catches": self.panel_catches,
            "known_bad_total": self.known_bad_total,
            "panel_catch_rate": self.panel_catch_rate,
            "known_good_total": self.known_good_total,
            "known_good_approved": self.known_good_approved,
            "false_reject_rate": self.false_reject_rate,
            "caveat": self.caveat,
        }


def score_panel(
    panel: ReviewPanel, fixtures: tuple[SeededFixture, ...], *, seed: int = 0
) -> CatchRateReport:
    """Convene the panel over every fixture and tally against labels."""
    roles = [reviewer.role.value for reviewer in panel.reviewers]
    role_catches = {role: 0 for role in roles}
    bad_total = catches = good_total = good_approved = 0
    for fixture in fixtures:
        evidence = fixture.internal + fixture.replication
        report = panel.convene(fixture.candidate, evidence, seed=seed)
        if fixture.kind == FixtureKind.KNOWN_GOOD:
            good_total += 1
            if report.outcome == PanelOutcome.APPROVED:
                good_approved += 1
        elif fixture.kind in KNOWN_BAD_KINDS:
            bad_total += 1
            if report.outcome == PanelOutcome.REJECTED:
                catches += 1
            substantive_roles = {
                objection.role.value
                for objection in (
                    obj for rnd in report.rounds for obj in rnd.objections()
                )
                if objection.severity in (Severity.MAJOR, Severity.BLOCKING)
            }
            for role in substantive_roles:
                if role in role_catches:
                    role_catches[role] += 1
    return CatchRateReport(
        tuple(
            RoleCatchStats(role, role_catches[role], bad_total) for role in sorted(role_catches)
        ),
        catches,
        bad_total,
        good_total,
        good_approved,
    )
