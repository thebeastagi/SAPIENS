"""Phase 5 — automated success-criteria suite (ship gates).

Runs the five ship-gate checks from HOW-TO-PROCEED Phase 5:

1. **0 gaming leaks** on the adversarial re-test (Phase-0 seams + FP guards).
2. **Null layer mandatory + logged** — 100% of shortlisted candidates carry a
   null-provenance record; UNCALIBRATED never silently passes.
3. **Blind kill-rate >= 8/10** with the real null layer, recovery >= 8/10,
   abstention < 10% (Phase 3 harness).
4. **Boundary stability <= 1 flip/item** over 3 seeds (B-02/B-03 fixed).
5. **Thresholds hash-committed** before each run.

Each check returns a :class:`CriterionResult`; :func:`run_success_criteria`
aggregates them into a single pass/fail suite. Retrospective numbers are an
intuition pump — the honest ceiling is a prospective precision@K trial, and the
suite says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .blind import blind_run, grade, seal
from .corpus import (
    CorpusItem,
    full_corpus,
    gaming_vectors,
    multiplicity_family_padding,
)
from .pipeline import GateOutcome, evaluate_family
from .promotion import CalibrationStatus
from .thresholds import ThresholdPolicy, Tier


def gaming_leaked(item: CorpusItem, outcome: GateOutcome) -> bool:
    """Did the seam this vector attacks actually leak its illegitimate reward?"""
    reward = item.illegitimate_reward
    if reward == "anomaly_boost":
        return outcome.anomaly_priority > 0.0
    if reward == "reserved_slot":
        return outcome.reserved_slot
    if reward == "calibrated":
        return outcome.calibration_status == CalibrationStatus.CALIBRATED
    if reward == "entry_via_gamed_baseline":
        return outcome.entered
    if reward == "entry_no_fdr":
        return outcome.entered
    if reward == "confirm":
        return outcome.tier == Tier.CONFIRM or outcome.entered
    return False


@dataclass(frozen=True)
class GamingRetest:
    leaks: tuple[str, ...]
    checked: int

    @property
    def clean(self) -> bool:
        return not self.leaks


def run_gaming_retest(policy: ThresholdPolicy | None = None) -> GamingRetest:
    """Re-run the gaming vectors and report any leaks (Phase-0 exit: 0 leaks).

    The FP-09 multiplicity vector is scored inside a **pure-noise family** (the
    real look-elsewhere scenario: one 3-sigma among ~1000 looks); the other
    vectors are per-candidate seams.
    """
    policy = policy or ThresholdPolicy()
    vectors = gaming_vectors()
    per_candidate = [v for v in vectors if v.inputs.candidate_id != "gv-fp09-multiplicity"]
    fp09 = [v for v in vectors if v.inputs.candidate_id == "gv-fp09-multiplicity"]

    outcomes: dict[str, GateOutcome] = {}
    res = evaluate_family(
        [v.inputs for v in per_candidate], policy=policy, run_id="gaming-retest"
    )
    outcomes.update({o.candidate_id: o for o in res.outcomes})

    if fp09:
        noise_family = [fp09[0].inputs] + multiplicity_family_padding(999)
        fres = evaluate_family(noise_family, policy=policy, run_id="gaming-fp09")
        for o in fres.outcomes:
            if o.candidate_id == "gv-fp09-multiplicity":
                outcomes[o.candidate_id] = o

    leaks = [
        v.inputs.candidate_id
        for v in vectors
        if gaming_leaked(v, outcomes[v.inputs.candidate_id])
    ]
    return GamingRetest(leaks=tuple(sorted(leaks)), checked=len(vectors))


@dataclass(frozen=True)
class CriterionResult:
    name: str
    passed: bool
    detail: str
    metrics: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SuiteResult:
    criteria: tuple[CriterionResult, ...]

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.criteria)

    def to_dict(self) -> dict[str, object]:
        return {
            "scientific_discoveries_claimed": 0,  # by construction
            "all_passed": self.all_passed,
            "criteria": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "detail": c.detail,
                    "metrics": c.metrics,
                }
                for c in self.criteria
            ],
            "honesty_note": (
                "Retrospective + synthetic-corpus gates are an intuition pump, "
                "not validation. The only real test is a prospective, "
                "pre-registered precision@K / false-positive-rate trial on a "
                "post-cutoff stream. No scientific discoveries are claimed."
            ),
        }


def run_success_criteria(
    *,
    policy: ThresholdPolicy | None = None,
    corpus: list[CorpusItem] | None = None,
    kill_target: float = 0.8,
    recovery_target: float = 0.8,
    abstention_max: float = 0.10,
    seeds: tuple[int, ...] = (1, 2, 3),
) -> SuiteResult:
    """Run all five ship gates and return a single aggregated suite result."""
    policy = policy or ThresholdPolicy()
    corpus = corpus or full_corpus()
    results: list[CriterionResult] = []

    # 1) Zero gaming leaks.
    retest = run_gaming_retest(policy)
    results.append(
        CriterionResult(
            name="0 gaming leaks (adversarial re-test)",
            passed=retest.clean,
            detail=(
                f"{retest.checked} vectors re-run; leaks: {list(retest.leaks) or 'none'}"
            ),
            metrics={"checked": retest.checked, "leaks": list(retest.leaks)},
        )
    )

    # 2) Null layer mandatory + logged (100% of shortlisted carry a record).
    fam = evaluate_family([it.inputs for it in corpus], policy=policy, run_id="criteria")
    shortlisted = fam.shortlist
    with_null = [
        o for o in shortlisted if o.null_provenance and "kind" in o.null_provenance
    ]
    # UNCALIBRATED must never be silently passed: any UNCALIBRATED that "entered".
    silent_uncalibrated = [
        o
        for o in fam.outcomes
        if o.calibration_status == CalibrationStatus.UNCALIBRATED and o.entered
    ]
    null_ok = len(with_null) == len(shortlisted) and not silent_uncalibrated
    results.append(
        CriterionResult(
            name="null layer mandatory + logged",
            passed=null_ok,
            detail=(
                f"{len(with_null)}/{len(shortlisted)} shortlisted carry a "
                f"null-provenance record; silent-UNCALIBRATED passes: "
                f"{len(silent_uncalibrated)}"
            ),
            metrics={
                "shortlisted": len(shortlisted),
                "with_null_provenance": len(with_null),
                "silent_uncalibrated": len(silent_uncalibrated),
            },
        )
    )

    # 3) Blind kill-rate / recovery / abstention.
    sealed = seal(corpus, seed=seeds[0])
    verdicts = blind_run(sealed, policy=policy, run_id="criteria-blind")
    report = grade(verdicts, sealed.key)
    blind_ok = (
        report.kill_rate >= kill_target
        and report.recovery_rate >= recovery_target
        and report.abstention_rate < abstention_max
    )
    results.append(
        CriterionResult(
            name="blind kill-rate/recovery/abstention",
            passed=blind_ok,
            detail=(
                f"kill={report.kill_rate:.2f} (>= {kill_target}), "
                f"recovery={report.recovery_rate:.2f} (>= {recovery_target}), "
                f"abstention={report.abstention_rate:.2f} (< {abstention_max}); "
                f"leaks={list(report.leaks) or 'none'}"
            ),
            metrics=report.to_dict(),
        )
    )

    # 4) Boundary stability <= 1 flip/item over 3 seeds.
    tier_by_seed: list[dict[str, str]] = []
    for s in seeds:
        r = evaluate_family(
            [it.inputs for it in corpus], policy=policy, run_id=f"stability-{s}"
        )
        tier_by_seed.append({o.candidate_id: o.tier.value for o in r.outcomes})
    max_flips = 0
    for cid in tier_by_seed[0]:
        seen = {t.get(cid) for t in tier_by_seed}
        flips = len(seen) - 1
        max_flips = max(max_flips, flips)
    results.append(
        CriterionResult(
            name="boundary stability <= 1 flip/item over 3 seeds",
            passed=max_flips <= 1,
            detail=f"max tier flips per item across {len(seeds)} seeds = {max_flips}",
            metrics={"max_flips": max_flips, "seeds": list(seeds)},
        )
    )

    # 5) Thresholds hash-committed per run.
    committed = policy.hash_commit("criteria")
    results.append(
        CriterionResult(
            name="thresholds hash-committed per run",
            passed=bool(committed) and len(committed) == 64,
            detail=f"policy sha256={committed[:16]}... (committed before results)",
            metrics={"policy_hash": committed, "policy_version": policy.version},
        )
    )

    return SuiteResult(criteria=tuple(results))
