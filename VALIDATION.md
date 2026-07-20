# Validation

## Local validation commands

```bash
python -m pip install -e ".[dev]"
ruff check src tests
pytest
python -m sapiens.cli
```

## Test coverage in Phase 0

- Ledger replay and hash-chain verification.
- Mutation/tamper detection.
- Illegal L0→L2 skip rejection.
- L4 human-gate enforcement.
- Demotion with reason and evidence.
- Synthetic kernel L0→L1→L2→L3 happy path.
- Bad synthetic candidate stays at L0.
- Cross-domain transfer creates a distinct L0 target candidate and links parent provenance.
- CLI demo asserts zero scientific-discovery claims.
- Queue capacity, idempotency, stale-lease rejection, oversized-payload rejection.
- Daemon executes only registered handlers under bounded context.
- Boundary test: core modules do not import synthetic adapters.
- Phase-0 rejects non-synthetic adapters (superseded in Phase 1 by trust-tier tests).

## CI

GitHub Actions runs Python 3.10, 3.11, and 3.12 with:

- editable install,
- `ruff check src tests`,
- `pytest`,
- import smoke.

## Security checklist

1. No secrets in repository; no `.env` files.
2. No upstream source copied from unlicensed repos.
3. No dynamic import, `eval`, pickle, or shell execution from queue payloads.
4. Queue payload bytes and active job counts are bounded.
5. Work uses monotonic in-process budgets and cooperative preemption safe points.
6. Ledger uses canonical JSON and rejects hash/sequence/transition violations.
7. Cross-domain bridge discards source confidence and starts target at L0.

## Phase 1–2 additions

- Trust-tier registry: third-party adapters refused without permission; tier derivation from manifest facts.
- Isolation: CPU-hog / memory-hog / sleeper children killed and contained; protocol corruption impossible from child stdout.
- Checkpoints: continuity verified; HMAC sign/verify; wrong-key detection; anchor export/verify.
- L1 gate: determinism, degenerate-score, missing-score rejection.
- L2 gate: holdout discipline, dataset-collision and (dataset, seed) leakage rejection, pass-fraction threshold.
- Calibration: fixture labels verified against gate behaviour; report rates match ground truth.
- Confidence: refuses without calibration / with thin calibration / without evidence.

## Known limits

- Hash-chain integrity is not cryptographic authorship or external timestamping.
- rlimits bound resource use but are not a full security sandbox; third-party code additionally requires a recorded owner permission.
- HMAC checkpoint signatures are symmetric: key possession, not third-party authorship.
- Confidence values are documented heuristics (raw pass fraction × demonstrated catch rate), not probability estimates; fixture suites are small and rates are exact only for the fixtures included.
- The daemon is cooperative and in-process for SYNTHETIC/CORE tiers; UNTRUSTED adapters run via subprocess isolation.
- Synthetic adapters are toy harnesses, not scientific models.
- L3 is represented as a bounded `review` evidence gate; full multi-agent review panels are roadmap.
- L4 is only a human-gated transition rule, not automated.
