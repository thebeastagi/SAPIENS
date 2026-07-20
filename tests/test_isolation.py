import pytest
from isolation_doubles import (
    BadEvidenceAdapter,
    CpuHogAdapter,
    MemoryHogAdapter,
    NoisyAdapter,
    SleeperAdapter,
    WellBehavedAdapter,
)

from sapiens.budget import ExecutionContext
from sapiens.isolation import (
    IsolationError,
    ResourceLimits,
    run_validate_isolated,
)
from sapiens.models import Candidate

CANDIDATE = Candidate("cand-1", "iso-domain", "isolated validation works", {"k": 1})
CONTEXT = ExecutionContext(max_steps=10, max_seconds=5.0)
FAST_LIMITS = ResourceLimits(cpu_seconds=2, address_space_bytes=256 << 20, max_open_files=32)


def test_well_behaved_adapter_round_trips_evidence():
    evidence = run_validate_isolated(
        WellBehavedAdapter(), CANDIDATE, stage="internal", seed=7, context=CONTEXT
    )
    assert len(evidence) == 1
    item = evidence[0]
    assert item.candidate_id == "cand-1"
    assert item.kind == "internal"
    assert item.passed is True
    assert item.score == 0.75
    assert item.details["isolated"] is True


def test_noisy_adapter_stdout_does_not_corrupt_protocol():
    evidence = run_validate_isolated(
        NoisyAdapter(), CANDIDATE, stage="internal", seed=7, context=CONTEXT
    )
    assert len(evidence) == 1 and evidence[0].passed


def test_cpu_hog_killed_by_rlimit():
    with pytest.raises(IsolationError, match="died"):
        run_validate_isolated(
            CpuHogAdapter(),
            CANDIDATE,
            stage="internal",
            seed=7,
            context=CONTEXT,
            limits=FAST_LIMITS,
            timeout_seconds=20.0,
        )


def test_memory_hog_contained_by_rlimit():
    with pytest.raises(IsolationError):
        run_validate_isolated(
            MemoryHogAdapter(),
            CANDIDATE,
            stage="internal",
            seed=7,
            context=CONTEXT,
            limits=FAST_LIMITS,
            timeout_seconds=20.0,
        )


def test_sleeper_killed_by_wall_clock_timeout():
    with pytest.raises(IsolationError, match="wall-clock"):
        run_validate_isolated(
            SleeperAdapter(),
            CANDIDATE,
            stage="internal",
            seed=7,
            context=CONTEXT,
            timeout_seconds=2.0,
        )


def test_invalid_adapter_evidence_is_contained():
    with pytest.raises(IsolationError):
        run_validate_isolated(
            BadEvidenceAdapter(), CANDIDATE, stage="internal", seed=7, context=CONTEXT
        )


def test_non_serialisable_candidate_parameters_rejected_before_spawn():
    candidate = Candidate("cand-2", "iso-domain", "bad params", {"fn": object()})
    with pytest.raises(IsolationError, match="JSON"):
        run_validate_isolated(
            WellBehavedAdapter(), candidate, stage="internal", seed=7, context=CONTEXT
        )


def test_locally_defined_adapter_cannot_be_isolated():
    class Local(WellBehavedAdapter):
        pass

    with pytest.raises(IsolationError, match="module level"):
        run_validate_isolated(
            Local(), CANDIDATE, stage="internal", seed=7, context=CONTEXT
        )
