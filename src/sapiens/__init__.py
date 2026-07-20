"""SAPIENS: experimental, traceable scientific-discovery workflow plumbing."""

from .adapter import DomainAdapter
from .bridge import TransferEnvelope, transfer
from .kernel import DiscoveryKernel
from .ledger import EvidenceLedger
from .models import AdapterManifest, Candidate, Evidence, EvidenceLevel
from .permissions import PermissionEntry, PermissionManifest
from .registry import AdapterRegistry, TrustTier

__all__ = [
    "AdapterManifest",
    "AdapterRegistry",
    "Candidate",
    "DiscoveryKernel",
    "DomainAdapter",
    "Evidence",
    "EvidenceLedger",
    "EvidenceLevel",
    "PermissionEntry",
    "PermissionManifest",
    "TransferEnvelope",
    "TrustTier",
    "transfer",
]
__version__ = "0.2.0"
