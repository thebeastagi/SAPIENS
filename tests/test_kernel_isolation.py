import json
from datetime import date

import pytest
from isolation_doubles import WellBehavedAdapter

from sapiens.budget import ExecutionContext
from sapiens.kernel import DiscoveryKernel
from sapiens.ledger import EvidenceLedger
from sapiens.models import Candidate, EvidenceLevel
from sapiens.permissions import MissingPermissionError, PermissionManifest
from sapiens.registry import AdapterRegistry

PERMISSION = {
    "source": "doubles",
    "scope": "adapter:well-behaved",
    "licence": "MIT",
    "granted_by": "owner@example.org",
    "reference": "https://example.org/permission/1",
    "granted_on": "2026-07-01",
    "expires_on": None,
}


def registry(tmp_path, entries):
    path = tmp_path / "permissions.json"
    path.write_text(json.dumps({"version": 1, "entries": entries}))
    return AdapterRegistry(PermissionManifest.load(path), today=date(2026, 7, 20))


def candidate():
    return Candidate("iso-cand", "iso-domain", "claim under isolation")


def test_kernel_runs_untrusted_adapter_isolated(tmp_path):
    kernel = DiscoveryKernel(
        EvidenceLedger(tmp_path / "evidence.jsonl"), registry(tmp_path, [PERMISSION])
    )
    cand = candidate()
    kernel.register(cand)
    reached = kernel.validate_next(
        WellBehavedAdapter(),
        cand,
        seed=7,
        context=ExecutionContext(max_steps=10, max_seconds=5.0),
    )
    assert reached == EvidenceLevel.L1
    state = kernel.ledger.state("iso-cand")
    assert state.level == EvidenceLevel.L1


def test_kernel_refuses_third_party_without_permission(tmp_path):
    kernel = DiscoveryKernel(
        EvidenceLedger(tmp_path / "evidence.jsonl"), registry(tmp_path, [])
    )
    cand = candidate()
    kernel.register(cand)
    with pytest.raises(MissingPermissionError):
        kernel.validate_next(
            WellBehavedAdapter(),
            cand,
            seed=7,
            context=ExecutionContext(max_steps=10, max_seconds=5.0),
        )
    # No promotion, no evidence: the ledger shows the candidate still at L0.
    assert kernel.ledger.state("iso-cand").level == EvidenceLevel.L0
