"""Module-level adapter doubles for isolation tests.

Isolation loads adapters by source-file path in a child process, so these
must live at module level in an importable file (not inside test functions).
Not a pytest module (no test_ functions); ruff still applies.
"""

from __future__ import annotations

import time

from sapiens.models import AdapterManifest, Candidate, Evidence


class WellBehavedAdapter:
    manifest = AdapterManifest(
        "well-behaved",
        "1",
        "iso-domain",
        ("x",),
        synthetic_only=False,
        code_origin="third-party",
        third_party_source="doubles",
        data_sources=("https://example.org/public",),
    )

    def propose(self, *, seed: int, limit: int):
        return ()

    def validate(self, candidate, *, stage: str, seed: int, context):
        context.checkpoint()
        return (
            Evidence(
                f"ev-{candidate.candidate_id}-{stage}",
                candidate.candidate_id,
                stage,
                True,
                "double-protocol",
                f"double-{stage}",
                seed,
                0.75,
                {"isolated": True},
            ),
        )

    def import_structure(self, structure, *, candidate_id: str):
        return Candidate(candidate_id, "iso-domain", "claim")


class NoisyAdapter(WellBehavedAdapter):
    def validate(self, candidate, *, stage: str, seed: int, context):
        print("NOISE THAT MUST NOT CORRUPT THE PROTOCOL")  # noqa: T201
        return super().validate(candidate, stage=stage, seed=seed, context=context)


class CpuHogAdapter(WellBehavedAdapter):
    def validate(self, candidate, *, stage: str, seed: int, context):
        while True:
            pass


class MemoryHogAdapter(WellBehavedAdapter):
    def validate(self, candidate, *, stage: str, seed: int, context):
        blob = bytearray(1 << 31)  # 2 GiB, exceeds any test rlimit
        return blob  # unreachable under limits; keeps linters quiet about unused work


class SleeperAdapter(WellBehavedAdapter):
    def validate(self, candidate, *, stage: str, seed: int, context):
        time.sleep(30)
        return ()


class BadEvidenceAdapter(WellBehavedAdapter):
    def validate(self, candidate, *, stage: str, seed: int, context):
        return (
            Evidence(
                "ev-bad",
                candidate.candidate_id,
                stage,
                True,
                "double-protocol",
                "double-data",
                seed,
                1.5,  # out of range: model must reject on the parent side
            ),
        )
