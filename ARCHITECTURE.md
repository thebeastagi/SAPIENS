# SAPIENS Architecture (Phases 0–4)

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
  validation.py   L1/L2 automated gates + holdout protocols + leakage controls (Phase 2)
  fixtures.py     seeded-bias fixture suite with labelled outcomes (Phase 2)
  calibration.py  gate-performance calibration reports (Phase 2)
  confidence.py   calibration-gated confidence aggregation (Phase 2)
  review.py       L3 panel protocol: roles, objections, rounds, gates (Phase 3)
  reviewers.py    deterministic reference reviewers, four roles (Phase 3)
  catchrate.py    panel catch-rate scoring over seeded fixtures (Phase 3)
  ledger.py       JSONL hash-chain ledger and L0→L4 transition guard
  kernel.py       domain-neutral candidate registration and next-gate validation
  bridge.py       cross-domain structure transfer with mandatory L0 reset
  budget.py       cooperative step/time budgets and preemption exceptions
  queue.py        bounded SQLite job queue with leases/idempotency
  daemon.py       bounded background worker skeleton
  cli.py          synthetic-only demo
  adapters/       synthetic adapters + Phase-4 real-data Kepler adapter
                  (published-signal re-derivation; validators sandboxed
                  behind the adapter contract)
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

## Validation gates (Phase 2)

`DiscoveryKernel(validation=ValidationGates(...))` opts into automated L1/L2 gates. L1 runs statistical sanity checks over a candidate's internal evidence (determinism across identical reruns, degenerate constant scores, score presence). L2 requires a declared `HoldoutProtocol` for the domain and enforces holdout discipline: replication evidence must come from declared holdout datasets, dataset collisions and (dataset, seed) reuse across the boundary are leakage and reject the gate, and a minimum pass fraction applies. Gate verdicts are appended to `kernel.gate_log` (inspectable, recomputable) — the kernel never fabricates gate outcomes as ledger evidence. Gates are pure functions in `sapiens.validation`; `sapiens.fixtures` ships a labelled seeded-bias suite; `sapiens.calibration` scores gates against it; `sapiens.confidence` refuses to aggregate confidence without the resulting report.

## Real domain adapters (Phase 4)

`KeplerPhotometryAdapter` is the first non-synthetic adapter: first-party clean-room code over a bundled, checksum-pinned public NASA/MAST Kepler Q1 light curve (CORE trust tier, no permission entry needed, in-process). Its validators are staged behind the contract: internal = fold SNR on the full curve; replication = independent time-halves must each re-detect at the same period; review = adversarial odd/even, secondary-eclipse and harmonic checks. All transit arithmetic lives in `adapters/_transit.py`; the kernel sees only evidence. The adapter re-derives a published signal as validation — it claims no discovery — and ships negative controls (flat, tampered, shifted-period curves). A declared `kepler_holdout_protocol()` wires it into the Phase-2 gates, and the reference panel reviews it in Phase-3 integration tests.

## L3 review panels (Phase 3)

`DiscoveryKernel(panel=ReviewPanel(...))` gates L3 promotion on a structured panel. Reviewers are pure deterministic functions in four roles (statistician, domain theorist, methodologist, devil's advocate). The panel convenes bounded rounds; objections carry severity (MINOR/MAJOR/BLOCKING) and a tracked lifecycle (raised/sustained/withdrawn); reference reviewers escalate re-affirmed MAJOR findings to BLOCKING. Approval requires no sustained MAJOR/BLOCKING objection; MINOR caveats are recorded but non-fatal. The panel's verdict is recorded in the ledger as review evidence (`panel-transcript` dataset) — approval adds it to the promotion refs, rejection leaves the candidate at L2 with the rejection on record. `sapiens.catchrate` scores panels against the seeded fixture suite.

## Cross-domain bridge

`transfer(source, source_level, target_adapter, candidate_id)` extracts only a small structural envelope and returns a target-domain candidate plus `EvidenceLevel.L0`. The discarded source level is retained only as provenance. The target candidate must climb target-domain gates from scratch.

## Background daemon skeleton

`WorkQueue` gives bounded jobs, serialized payload-size limits, idempotency keys, leases, stale-lease rejection, and retry/dead states. `DiscoveryDaemon.run_bounded` executes only explicitly registered handlers under time/step budgets; it does not dynamically import or shell out from queue payloads.

Synthetic and CORE (first-party, real-data) adapters run in-process with cooperative preemption. UNTRUSTED (third-party) adapters run only via `sapiens.isolation`: a child process applies POSIX rlimits (CPU, address space, open files) to itself, the parent enforces a wall-clock timeout, and every failure mode is contained fail-closed (no evidence on failure). Third-party adapters additionally require a recorded owner permission (`permissions.json`, empty by default) before the registry will validate them at all. rlimits bound resources; they are not a full security sandbox.
