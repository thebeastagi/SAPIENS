"""SAPIENS: experimental, traceable scientific-discovery workflow plumbing."""

from .adapter import DomainAdapter
from .bridge import TransferEnvelope, transfer
from .calibration import CalibrationReport, run_calibration
from .catchrate import CatchRateReport, score_panel
from .confidence import CalibratedConfidence, UncalibratedError, aggregate_confidence
from .fixtures import FixtureKind, SeededFixture, fixture_suite
from .kernel import DiscoveryKernel
from .ledger import EvidenceLedger
from .models import AdapterManifest, Candidate, Evidence, EvidenceLevel
from .permissions import PermissionEntry, PermissionManifest
from .registry import AdapterRegistry, TrustTier
from .review import PanelOutcome, PanelReport, ReviewerRole, ReviewPanel
from .reviewers import reference_panel
from .validation import GateVerdict, HoldoutProtocol, ValidationGates

__all__ = [
    "AdapterManifest",
    "AdapterRegistry",
    "CalibratedConfidence",
    "CalibrationReport",
    "Candidate",
    "CatchRateReport",
    "DiscoveryKernel",
    "DomainAdapter",
    "Evidence",
    "EvidenceLedger",
    "EvidenceLevel",
    "FixtureKind",
    "GateVerdict",
    "HoldoutProtocol",
    "PanelOutcome",
    "PanelReport",
    "PermissionEntry",
    "PermissionManifest",
    "ReviewerRole",
    "ReviewPanel",
    "SeededFixture",
    "TransferEnvelope",
    "TrustTier",
    "UncalibratedError",
    "ValidationGates",
    "aggregate_confidence",
    "fixture_suite",
    "reference_panel",
    "run_calibration",
    "score_panel",
    "transfer",
]
__version__ = "0.4.0"
