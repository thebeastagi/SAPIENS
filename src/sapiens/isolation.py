"""Subprocess isolation with OS-level resource limits for untrusted adapters (Phase 1).

UNTRUSTED-tier adapters never execute in the kernel's process. Instead the
kernel serialises the work order (adapter location, candidate, stage, seed,
budget) to a child Python process that:

1. applies POSIX rlimits to *itself* before importing any adapter code
   (CPU seconds, address space, open files — thread-safe, unlike preexec_fn),
2. loads the adapter class from its source file, constructs it with no
   arguments, and runs ``validate`` under a fresh ``ExecutionContext``,
3. prints exactly one JSON result line on stdout (adapter stdout is
   redirected to stderr so a noisy adapter cannot corrupt the protocol).

The parent enforces a wall-clock timeout and maps every failure — crash,
limit kill, timeout, malformed output — to :class:`IsolationError`. Isolation
is fail-closed: a contained failure produces no evidence.

Honest limits: rlimits bound resource use; they are not a security sandbox.
A malicious adapter could still attempt network or filesystem mischief within
those bounds — which is why third-party code additionally requires a recorded
owner permission before it may run at all.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .budget import ExecutionContext
from .models import Candidate, Evidence

PROTOCOL_VERSION = 1


class IsolationError(RuntimeError):
    """An isolated run failed or its result could not be trusted."""


@dataclass(frozen=True)
class ResourceLimits:
    cpu_seconds: int = 30
    address_space_bytes: int = 1 << 30  # 1 GiB
    max_open_files: int = 64

    def __post_init__(self) -> None:
        if self.cpu_seconds <= 0 or self.address_space_bytes <= 0 or self.max_open_files <= 0:
            raise ValueError("resource limits must be positive")


DEFAULT_LIMITS = ResourceLimits()


def _apply_limits(limits: ResourceLimits) -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (limits.cpu_seconds, limits.cpu_seconds))
    resource.setrlimit(
        resource.RLIMIT_AS, (limits.address_space_bytes, limits.address_space_bytes)
    )
    resource.setrlimit(resource.RLIMIT_NOFILE, (limits.max_open_files, limits.max_open_files))


def _load_adapter(path: str, qualname: str) -> Any:
    if "<locals>" in qualname:
        raise IsolationError("isolated adapters must be module-level classes")
    spec = importlib.util.spec_from_file_location("sapiens_isolated_adapter", path)
    if spec is None or spec.loader is None:
        raise IsolationError(f"cannot load adapter module from {path!r}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    obj: Any = module
    for part in qualname.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            raise IsolationError(f"adapter class {qualname!r} not found in {path!r}")
    return obj()


def _serialize_evidence(item: Evidence) -> dict[str, Any]:
    return {
        "evidence_id": item.evidence_id,
        "candidate_id": item.candidate_id,
        "kind": item.kind,
        "passed": item.passed,
        "protocol": item.protocol,
        "dataset": item.dataset,
        "seed": item.seed,
        "score": item.score,
        "details": dict(item.details),
    }


def _child_main() -> None:
    """Entry point: ``python -m sapiens.isolation`` (reads the work order on stdin)."""
    try:
        spec = json.loads(sys.stdin.read())
        if spec.get("protocol") != PROTOCOL_VERSION:
            raise IsolationError("isolation protocol version mismatch")
        limits = ResourceLimits(**spec["limits"])
        _apply_limits(limits)
        adapter = _load_adapter(spec["adapter_path"], spec["adapter_qualname"])
        raw = spec["candidate"]
        candidate = Candidate(
            raw["candidate_id"],
            raw["domain"],
            raw["claim"],
            raw.get("parameters") or {},
            raw.get("parent_id"),
            raw.get("source_adapter", ""),
        )
        budget = spec["budget"]
        context = ExecutionContext(
            max_steps=int(budget["max_steps"]), max_seconds=float(budget["max_seconds"])
        )
        import contextlib

        with contextlib.redirect_stdout(sys.stderr):
            evidence = adapter.validate(
                candidate, stage=spec["stage"], seed=int(spec["seed"]), context=context
            )
        payload = [_serialize_evidence(item) for item in evidence]
        # Fail loudly inside the child if anything is not canonical-JSON safe.
        result = json.dumps(
            {"ok": True, "evidence": payload}, allow_nan=False, ensure_ascii=False
        )
    except BaseException as exc:  # contained: report, never traceback-spam the parent
        result = json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
    sys.stdout.write(result + "\n")
    sys.stdout.flush()


def adapter_location(adapter: object) -> tuple[str, str]:
    """(source file, qualname) for an adapter instance; raises if not locatable."""
    cls = type(adapter)
    path = inspect.getsourcefile(cls)
    if path is None or not Path(path).is_file():
        raise IsolationError(f"cannot locate source file for adapter class {cls.__name__!r}")
    qualname = cls.__qualname__
    if "<locals>" in qualname:
        raise IsolationError("isolated adapters must be defined at module level")
    return path, qualname


def run_validate_isolated(
    adapter: object,
    candidate: Candidate,
    *,
    stage: str,
    seed: int,
    context: ExecutionContext,
    limits: ResourceLimits = DEFAULT_LIMITS,
    timeout_seconds: float = 60.0,
) -> tuple[Evidence, ...]:
    """Run ``adapter.validate`` in a resource-limited subprocess. Fail-closed."""
    if sys.platform == "win32":
        raise IsolationError("subprocess isolation requires POSIX rlimits")
    if timeout_seconds <= 0:
        raise ValueError("timeout must be positive")
    path, qualname = adapter_location(adapter)
    spec = {
        "protocol": PROTOCOL_VERSION,
        "adapter_path": path,
        "adapter_qualname": qualname,
        "candidate": {
            "candidate_id": candidate.candidate_id,
            "domain": candidate.domain,
            "claim": candidate.claim,
            "parameters": dict(candidate.parameters),
            "parent_id": candidate.parent_id,
            "source_adapter": candidate.source_adapter,
        },
        "stage": stage,
        "seed": seed,
        "budget": {"max_steps": context.max_steps, "max_seconds": context.max_seconds},
        "limits": {
            "cpu_seconds": limits.cpu_seconds,
            "address_space_bytes": limits.address_space_bytes,
            "max_open_files": limits.max_open_files,
        },
    }
    try:
        order = json.dumps(spec, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise IsolationError(f"work order is not JSON-serialisable: {exc}") from exc
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "sapiens.isolation"],
            input=order,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise IsolationError(
            f"isolated adapter exceeded the {timeout_seconds}s wall-clock timeout"
        ) from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        detail = tail[-1] if tail else "no stderr"
        raise IsolationError(
            f"isolated adapter died (exit {proc.returncode}; killed by rlimit or crash): {detail}"
        )
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise IsolationError("isolated adapter produced malformed stdout")
    try:
        result = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise IsolationError("isolated adapter produced invalid JSON") from exc
    if not result.get("ok"):
        raise IsolationError(f"isolated adapter failed: {result.get('error', 'unknown')}")
    evidence: list[Evidence] = []
    for raw in result["evidence"]:
        try:
            evidence.append(Evidence(**raw))
        except (TypeError, ValueError) as exc:
            raise IsolationError(f"isolated adapter returned invalid evidence: {exc}") from exc
    return tuple(evidence)


if __name__ == "__main__":
    _child_main()
