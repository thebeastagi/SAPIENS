"""SAPIENS: experimental, traceable scientific-discovery workflow plumbing."""

from .adapter import DomainAdapter
from .bridge import TransferEnvelope, transfer
from .calibration import CalibrationReport, run_calibration
from .confidence import CalibratedConfidence, UncalibratedError, aggregate_confidence
from .fixtures import FixtureKind, SeededFixture, fixture_suite
from .kernel import DiscoveryKernel
from .ledger import EvidenceLedger
from .models import AdapterManifest, Candidate, Evidence, EvidenceLevel
from .permissions import PermissionEntry, PermissionManifest
from .registry import AdapterRegistry, TrustTier
from .validation import GateVerdict, HoldoutProtocol, ValidationGates

__all__ = [
    "AdapterManifest",
    "AdapterRegistry",
    "CalibratedConfidence",
    "CalibrationReport",
    "Candidate",
    "DiscoveryKernel",
    "DomainAdapter",
    "Evidence",
    "EvidenceLedger",
    "EvidenceLevel",
    "FixtureKind",
    "GateVerdict",
    "HoldoutProtocol",
    "PermissionEntry",
    "PermissionManifest",
    "SeededFixture",
    "TransferEnvelope",
    "TrustTier",
    "UncalibratedError",
    "ValidationGates",
    "aggregate_confidence",
    "fixture_suite",
    "run_calibration",
    "transfer",
]
__version__ = "0.3.0"
