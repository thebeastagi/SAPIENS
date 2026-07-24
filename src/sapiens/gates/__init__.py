"""Discovery-gate hardening (scout HOW-TO-PROCEED Phases 0-5).

A self-contained, stdlib-only subpackage that implements the anti-gaming +
null-layer + decoupled-threshold + blind-harness + human-gate + success-criteria
machinery on top of the SAPIENS foundation. It imports nothing from
``sapiens.adapters`` and copies no ASTRA/GEODISC/BIODISC/SLATE code — it is built
from the recalibration/how-to-proceed specs only. No scientific discoveries are
claimed; this is evidence-hygiene plumbing.
"""

from __future__ import annotations

from .blind import (
    BlindReport,
    CustodyKey,
    SealedSet,
    Verdict,
    blind_run,
    grade,
    seal,
    strip_to_blind,
)
from .corpus import (
    CorpusItem,
    decoys,
    full_corpus,
    gaming_vectors,
    historical_positives,
)
from .criteria import (
    CriterionResult,
    SuiteResult,
    run_gaming_retest,
    run_success_criteria,
)
from .devils_advocate import PermutationResult, devils_advocate_permutation, pearson_r
from .dossier import (
    Dossier,
    OverrideEvent,
    OverrideLog,
    autonomous_claim_eligible,
    build_dossier,
)
from .fdr import FDRResult, benjamini_hochberg, pvalue_to_sigma, sigma_to_pvalue
from .nulls import InstrumentSystematic, NullKind, NullProvenance, no_null
from .pipeline import FamilyResult, GateOutcome, evaluate_family
from .promotion import (
    CalibrationStatus,
    GateInputs,
    LedgerStatus,
    anomaly_priority,
    calibration_status,
    ledger_status,
    promotion_score,
    reserved_slot_eligible,
)
from .surprise import (
    LiteratureExpectation,
    RobustBaseline,
    is_surprising,
    measured_surprise,
    robust_baseline,
)
from .thresholds import (
    Domain,
    ThresholdPolicy,
    Tier,
    adaptive_ci_floor,
    confirm_decision,
    degree_of_calibration,
)

__all__ = [
    "BlindReport",
    "CalibrationStatus",
    "confirm_decision",
    "CorpusItem",
    "CriterionResult",
    "CustodyKey",
    "Domain",
    "Dossier",
    "FDRResult",
    "FamilyResult",
    "GateInputs",
    "GateOutcome",
    "InstrumentSystematic",
    "LedgerStatus",
    "LiteratureExpectation",
    "NullKind",
    "NullProvenance",
    "OverrideEvent",
    "OverrideLog",
    "PermutationResult",
    "RobustBaseline",
    "SealedSet",
    "SuiteResult",
    "ThresholdPolicy",
    "Tier",
    "Verdict",
    "adaptive_ci_floor",
    "anomaly_priority",
    "autonomous_claim_eligible",
    "benjamini_hochberg",
    "blind_run",
    "build_dossier",
    "calibration_status",
    "decoys",
    "degree_of_calibration",
    "devils_advocate_permutation",
    "evaluate_family",
    "full_corpus",
    "gaming_vectors",
    "grade",
    "historical_positives",
    "is_surprising",
    "ledger_status",
    "measured_surprise",
    "no_null",
    "pearson_r",
    "promotion_score",
    "pvalue_to_sigma",
    "reserved_slot_eligible",
    "robust_baseline",
    "run_gaming_retest",
    "run_success_criteria",
    "seal",
    "sigma_to_pvalue",
    "strip_to_blind",
]
