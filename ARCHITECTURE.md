# SAPIENS Architecture (Phases 0–1)

## Design goals

1. Separate domain knowledge from shared discovery mechanics.
2. Make every belief transition replayable from an append-only ledger.
3. Keep cross-domain transfer useful but epistemically conservative: transfer structure, never confidence.
4. Bound background autonomy with budgets, leases, and preemption.
5. Prove orchestration on small deterministic synthetic domains only.

## Package map

```text
src/sapiens/
  models.py       immutable candidate/evidence/manifest models
  adapter.py      DomainAdapter protocol; validation routes to the registry
  registry.py     trust-tiered adapter registry (Phase 1)
  permissions.py  owner-permission/licence manifest for third-party code (Phase 1)
  isolation.py    subprocess + rlimit execution for UNTRUSTED adapters (Phase 1)
  checkpoints.py  signed ledger checkpoints + external anchor export (Phase 1)
  ledger.py       JSONL hash-chain ledger and L0→L4 transition guard
  kernel.py       domain-neutral candidate registration and next-gate validation
  bridge.py       cross-domain structure transfer with mandatory L0 reset
  budget.py       cooperative step/time budgets and preemption exceptions
  queue.py        bounded SQLite job queue with leases/idempotency
  daemon.py       bounded background worker skeleton
  cli.py          synthetic-only demo
  adapters/       two deterministic synthetic adapters
```

Dependency rule: `sapiens` core modules do not import `sapiens.adapters`; tests enforce this. Adapters import core contracts.

## DomainAdapter contract

Adapters may propose candidates and produce evidence, but they cannot set evidence level or append ledger events directly. The kernel owns promotion/demotion through `EvidenceLedger`.

Required methods:

- `manifest`: domain name/version/vocabulary plus provenance facts
  (`synthetic_only`, `code_origin`, `data_sources`, `third_party_source`).
  The Phase-1 registry derives a trust tier from these facts.
- `propose(seed, limit)`: deterministic candidates.
- `validate(candidate, stage, seed, context)`: bounded evidence for `internal`, `replication`, or `review`.
- `import_structure(structure, candidate_id)`: target-domain candidate from cross-domain structure.

## Evidence ledger

The ledger is newline-delimited canonical JSON. Each event stores the previous event hash and its own hash. Replay validates sequence, hashes, candidate creation, evidence scope, one-step promotion, required evidence kinds, demotion reasons, and the L4 human gate.

Hash chaining detects tampering but does **not** prove authorship, scientific truth, or external timestamping. Phase-1 `checkpoint` events summarise the chain (event count + head hash) and may carry an HMAC-SHA256 signature (environment-held key, never stored); `sapiens.checkpoints` also exports/verifies external anchor files. HMAC is symmetric: it proves key possession, not third-party authorship.

## Cross-domain bridge

`transfer(source, source_level, target_adapter, candidate_id)` extracts only a small structural envelope and returns a target-domain candidate plus `EvidenceLevel.L0`. The discarded source level is retained only as provenance. The target candidate must climb target-domain gates from scratch.

## Background daemon skeleton

`WorkQueue` gives bounded jobs, serialized payload-size limits, idempotency keys, leases, stale-lease rejection, and retry/dead states. `DiscoveryDaemon.run_bounded` executes only explicitly registered handlers under time/step budgets; it does not dynamically import or shell out from queue payloads.

Synthetic and CORE (first-party, real-data) adapters run in-process with cooperative preemption. UNTRUSTED (third-party) adapters run only via `sapiens.isolation`: a child process applies POSIX rlimits (CPU, address space, open files) to itself, the parent enforces a wall-clock timeout, and every failure mode is contained fail-closed (no evidence on failure). Third-party adapters additionally require a recorded owner permission (`permissions.json`, empty by default) before the registry will validate them at all. rlimits bound resources; they are not a full security sandbox.
