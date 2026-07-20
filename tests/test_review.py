"""Panel protocol + schema tests (scripted reviewer doubles)."""

import json

import pytest

from sapiens.models import Candidate, Evidence
from sapiens.review import (
    Objection,
    ObjectionStatus,
    PanelOutcome,
    ReviewerRole,
    ReviewerVerdict,
    ReviewPanel,
    Severity,
    VerdictKind,
)

CANDIDATE = Candidate("cand-p", "dom", "a claim about signal")
EVIDENCE = (Evidence("e1", "cand-p", "internal", True, "p", "d", 1, 0.9),)


class Scripted:
    """Reviewer double following a per-round script of (verdict, [(severity, text)])."""

    def __init__(self, role, script):
        self.role = role
        self._script = script

    def review(self, candidate, evidence, *, round_number, prior_objections, seed):
        kind, objections = self._script.get(round_number, (VerdictKind.APPROVE, []))
        return ReviewerVerdict(
            self.role,
            kind,
            f"scripted round {round_number}",
            tuple(
                Objection(
                    f"{self.role.value}-r{round_number}-{i}",
                    self.role,
                    severity,
                    text,
                    round_number,
                )
                for i, (severity, text) in enumerate(objections)
            ),
        )


def approve_all(role):
    return Scripted(role, {})


class TestSchema:
    def test_approve_carries_no_objections(self):
        with pytest.raises(ValueError):
            ReviewerVerdict(
                ReviewerRole.STATISTICIAN,
                VerdictKind.APPROVE,
                "rationale",
                (Objection("o1", ReviewerRole.STATISTICIAN, Severity.MINOR, "x", 1),),
            )

    def test_object_requires_objections(self):
        with pytest.raises(ValueError):
            ReviewerVerdict(ReviewerRole.STATISTICIAN, VerdictKind.OBJECT, "rationale")

    def test_abstain_carries_no_objections(self):
        with pytest.raises(ValueError):
            ReviewerVerdict(
                ReviewerRole.STATISTICIAN,
                VerdictKind.ABSTAIN,
                "rationale",
                (Objection("o1", ReviewerRole.STATISTICIAN, Severity.MINOR, "x", 1),),
            )

    def test_rationale_required(self):
        with pytest.raises(ValueError):
            ReviewerVerdict(ReviewerRole.STATISTICIAN, VerdictKind.APPROVE, "")

    def test_objection_role_must_match(self):
        with pytest.raises(ValueError):
            ReviewerVerdict(
                ReviewerRole.STATISTICIAN,
                VerdictKind.OBJECT,
                "rationale",
                (Objection("o1", ReviewerRole.METHODOLOGIST, Severity.MINOR, "x", 1),),
            )

    def test_objection_needs_text_and_valid_round(self):
        with pytest.raises(ValueError):
            Objection("o1", ReviewerRole.STATISTICIAN, Severity.MINOR, "", 1)
        with pytest.raises(ValueError):
            Objection("o1", ReviewerRole.STATISTICIAN, Severity.MINOR, "x", 0)

    def test_panel_requires_unique_roles_and_budget(self):
        with pytest.raises(ValueError):
            ReviewPanel(())
        with pytest.raises(ValueError):
            ReviewPanel((approve_all(ReviewerRole.STATISTICIAN),) * 2)
        with pytest.raises(ValueError):
            ReviewPanel((approve_all(ReviewerRole.STATISTICIAN),), max_rounds=0)


class TestProtocol:
    def panel(self, *reviewers, max_rounds=3):
        return ReviewPanel(reviewers, max_rounds=max_rounds)

    def test_clean_consensus_approves_in_one_round(self):
        panel = self.panel(
            approve_all(ReviewerRole.STATISTICIAN), approve_all(ReviewerRole.METHODOLOGIST)
        )
        report = panel.convene(CANDIDATE, EVIDENCE, seed=1)
        assert report.outcome == PanelOutcome.APPROVED
        assert len(report.rounds) == 1

    def test_minor_raised_then_withdrawn_approves(self):
        wavering = Scripted(
            ReviewerRole.STATISTICIAN,
            {1: (VerdictKind.OBJECT, [(Severity.MINOR, "caveat")])},
        )
        panel = self.panel(wavering, approve_all(ReviewerRole.METHODOLOGIST))
        report = panel.convene(CANDIDATE, EVIDENCE, seed=1)
        assert report.outcome == PanelOutcome.APPROVED
        assert len(report.rounds) == 2
        assert [status for _, status in report.lifecycle] == [ObjectionStatus.WITHDRAWN]
        assert report.withdrawn[0].text == "caveat"

    def test_major_escalates_and_rejects(self):
        # The raiser holds the objection through the whole budget: MAJOR in
        # round 1, escalated to BLOCKING in the rebuttals, never withdrawn.
        escalating = Scripted(
            ReviewerRole.STATISTICIAN,
            {
                1: (VerdictKind.OBJECT, [(Severity.MAJOR, "suspicious")]),
                2: (VerdictKind.OBJECT, [(Severity.BLOCKING, "suspicious")]),
                3: (VerdictKind.OBJECT, [(Severity.BLOCKING, "suspicious")]),
            },
        )
        panel = self.panel(escalating, approve_all(ReviewerRole.METHODOLOGIST))
        report = panel.convene(CANDIDATE, EVIDENCE, seed=1)
        assert report.outcome == PanelOutcome.REJECTED
        assert len(report.rounds) == 3
        assert report.sustained_blocking[0].text == "suspicious"
        statuses = dict(report.lifecycle)
        assert list(statuses.values()) == [ObjectionStatus.SUSTAINED]

    def test_escalated_objection_late_withdrawal_approves(self):
        # Escalated to BLOCKING in round 2, then withdrawn in round 3: the
        # lifecycle must record the withdrawal and the panel approves.
        relenting = Scripted(
            ReviewerRole.STATISTICIAN,
            {
                1: (VerdictKind.OBJECT, [(Severity.MAJOR, "suspicious")]),
                2: (VerdictKind.OBJECT, [(Severity.BLOCKING, "suspicious")]),
            },
        )
        panel = self.panel(relenting, approve_all(ReviewerRole.METHODOLOGIST))
        report = panel.convene(CANDIDATE, EVIDENCE, seed=1)
        assert report.outcome == PanelOutcome.APPROVED
        assert len(report.rounds) == 3
        assert report.withdrawn[0].text == "suspicious"
        assert report.withdrawn[0].severity == Severity.BLOCKING

    def test_blocking_withdrawn_in_rebuttal_approves(self):
        relenting = Scripted(
            ReviewerRole.DEVILS_ADVOCATE,
            {1: (VerdictKind.OBJECT, [(Severity.BLOCKING, "fatal flaw")])},
        )
        panel = self.panel(relenting, approve_all(ReviewerRole.METHODOLOGIST))
        report = panel.convene(CANDIDATE, EVIDENCE, seed=1)
        assert report.outcome == PanelOutcome.APPROVED
        assert len(report.rounds) == 2
        assert report.withdrawn[0].text == "fatal flaw"

    def test_residual_minor_is_caveat_not_fatal(self):
        stubborn_minor = Scripted(
            ReviewerRole.METHODOLOGIST,
            {
                1: (VerdictKind.OBJECT, [(Severity.MINOR, "nit")]),
                2: (VerdictKind.OBJECT, [(Severity.MINOR, "nit")]),
                3: (VerdictKind.OBJECT, [(Severity.MINOR, "nit")]),
            },
        )
        panel = self.panel(stubborn_minor, approve_all(ReviewerRole.STATISTICIAN))
        report = panel.convene(CANDIDATE, EVIDENCE, seed=1)
        assert report.outcome == PanelOutcome.APPROVED
        assert len(report.rounds) == 3  # budget exhausted on the caveat

    def test_sustained_major_at_budget_rejects(self):
        stubborn_major = Scripted(
            ReviewerRole.METHODOLOGIST,
            {
                1: (VerdictKind.OBJECT, [(Severity.MAJOR, "concern")]),
                2: (VerdictKind.OBJECT, [(Severity.MAJOR, "concern")]),
                3: (VerdictKind.OBJECT, [(Severity.MAJOR, "concern")]),
            },
        )
        panel = self.panel(stubborn_major, approve_all(ReviewerRole.STATISTICIAN))
        report = panel.convene(CANDIDATE, EVIDENCE, seed=1)
        assert report.outcome == PanelOutcome.REJECTED
        assert len(report.rounds) == 3

    def test_report_serialisable_and_deterministic_id(self):
        panel = self.panel(approve_all(ReviewerRole.STATISTICIAN))
        first = panel.convene(CANDIDATE, EVIDENCE, seed=1)
        second = panel.convene(CANDIDATE, EVIDENCE, seed=1)
        assert first.report_id == second.report_id
        blob = json.dumps(first.to_dict())
        assert "cand-p" in blob and "approved" in blob
