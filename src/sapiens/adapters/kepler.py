"""Real-data Kepler photometry adapter (Phase 4).

The first non-synthetic SAPIENS adapter: it re-derives the **already known,
published** Kepler-10 b transit signal (Batalha et al. 2011) from a small
public NASA/MAST Quarter-1 light curve bundled as package data. This is a
validation of a published result against an answer key — **not a discovery,
and nothing here claims one**. The candidate claim is deliberately a
measurement statement ("periodic transit-like dimming"), never a planet
claim.

Clean-room boundary: the transit arithmetic is ported from this
repository's own Apache-2.0 `demos/ledger-grok` pipeline. Zero code from
ASTRA / GEODISC / BIODISC / SLATE. The adapter registers at CORE trust tier
(first-party clean-room code, real public data). All domain validators live
behind this adapter; the kernel sees only contract evidence.

Determinism: the analysis has no random component; the contract ``seed`` is
accepted and recorded but does not alter results.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sapiens.budget import ExecutionContext
from sapiens.models import AdapterManifest, Candidate, Evidence
from sapiens.validation import HoldoutProtocol

from . import _transit

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_DATA = DATA_DIR / "kepler10_kic11904151_q1_lc.csv"
# Pinned integrity for the bundled public curve (sha256 of the file).
EXPECTED_SHA256 = "1d82ef8ced447bb44ac80c7389a8ef3dde93bf1983d619d56fe2f6cda3a56ded"

MAST_SOURCE = (
    "https://mast.stsci.edu (NASA Kepler public archive): KIC 11904151 Q1 PDCSAP"
)
PUBLISHED_PERIOD_DAYS = 0.8374912  # NASA Exoplanet Archive, Kepler-10 b

# Gate thresholds (documented, deterministic).
PROPOSE_SNR_FLOOR = 6.0
INTERNAL_SNR_THRESHOLD = 10.0
REPLICATION_SNR_THRESHOLD = 5.0
REPLICATION_PERIOD_TOLERANCE = 0.02
REVIEW_ODD_EVEN_SIGMA = 3.0
REVIEW_SECONDARY_SIGMA = 4.0

DATASET_FULL = "kepler-q1-full"
DATASET_HALVES = "kepler-q1-holdout-halves"
DATASET_REVIEW = "kepler-q1-review-adversarial"


def kepler_holdout_protocol() -> HoldoutProtocol:
    """Declared train/holdout split for this domain (Phase-2 wiring)."""
    return HoldoutProtocol(
        "kepler-q1-v1",
        train_datasets=(DATASET_FULL,),
        holdout_datasets=(DATASET_HALVES, DATASET_REVIEW),
    )


def _identifier(*parts: object) -> str:
    return hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:20]


def verify_data_integrity(path: Path) -> None:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise _transit.DataIntegrityError(
            f"bundled light curve checksum mismatch: {digest} != {EXPECTED_SHA256}"
        )


class KeplerPhotometryAdapter:
    """Re-derivation adapter over the bundled public Kepler Q1 light curve."""

    manifest = AdapterManifest(
        name="kepler-photometry",
        version="1.0",
        domain="kepler-photometry",
        vocabulary=("time", "flux", "period", "transit", "depth", "epoch", "snr"),
        synthetic_only=False,
        code_origin="first-party-clean-room",
        data_sources=(MAST_SOURCE,),
    )

    def __init__(
        self,
        data_path: str | Path | None = None,
        *,
        nfreq: int = 1500,
        verify_checksum: bool = True,
    ) -> None:
        self._path = Path(data_path) if data_path is not None else DEFAULT_DATA
        if verify_checksum and self._path == DEFAULT_DATA:
            verify_data_integrity(self._path)
        self._nfreq = nfreq
        self._cache: dict[str, object] = {}

    # -- data handling -----------------------------------------------------

    def _curve(self) -> tuple[list[float], list[float], list[float], int]:
        if "curve" not in self._cache:
            times, fluxes = _transit.load_csv(self._path)
            times, fluxes, masked = _transit.apply_mask(times, fluxes)
            detrended = _transit.detrend(times, fluxes)
            self._cache["curve"] = (times, fluxes, detrended, masked)
        return self._cache["curve"]  # type: ignore[return-value]

    def _search(self) -> dict:
        if "search" not in self._cache:
            times, _, y, _ = self._curve()
            self._cache["search"] = _transit.bls(times, y, nfreq=self._nfreq)
        return self._cache["search"]  # type: ignore[return-value]

    # -- DomainAdapter contract ---------------------------------------------

    def propose(self, *, seed: int, limit: int) -> tuple[Candidate, ...]:
        """Bounded BLS search; propose the strongest periodic transit candidate.

        Returns an empty tuple when the curve shows no signal above the SNR
        floor — proposing nothing is the honest negative result.
        """
        if limit <= 0:
            return ()
        times, _, y, _ = self._curve()
        search = self._search()
        measured = _transit.fold_measure(
            times, y, search["period_days"], search["phase_center"], search["q"]
        )
        if measured["snr"] < PROPOSE_SNR_FLOOR:
            return ()
        period = search["period_days"]
        candidate = Candidate(
            _identifier(self.manifest.name, "kic11904151-q1", f"{period:.7f}"),
            self.manifest.domain,
            "KIC 11904151 Q1 photometry shows periodic transit-like dimming "
            f"at period {period:.6f} d (re-derivation of a published signal; "
            "not a discovery)",
            {
                "relation": "periodic-transit",
                "arity": 1,
                "period": period,
                "q": search["q"],
                "phase_center": search["phase_center"],
                "depth_ppm": measured["depth_ppm"],
                "snr": measured["snr"],
                "epoch_bkjd": measured["epoch_bkjd"],
            },
            source_adapter=self.manifest.name,
        )
        return (candidate,)[:limit]

    def validate(
        self, candidate: Candidate, *, stage: str, seed: int, context: ExecutionContext
    ) -> tuple[Evidence, ...]:
        context.checkpoint()
        if stage == "internal":
            return self._validate_internal(candidate, seed)
        if stage == "replication":
            return self._validate_replication(candidate, seed, context)
        if stage == "review":
            return self._validate_review(candidate, seed, context)
        raise ValueError(f"unknown stage {stage!r}")

    def import_structure(self, structure: dict[str, object], *, candidate_id: str) -> Candidate:
        period = structure.get("period")
        return Candidate(
            candidate_id,
            self.manifest.domain,
            "test a transferred periodic-transit structure against the bundled "
            "Kepler Q1 light curve (validation, not a discovery)",
            {
                "relation": "periodic-transit",
                "arity": structure.get("arity", 1),
                "period": float(period) if period is not None else PUBLISHED_PERIOD_DAYS,
            },
            parent_id=str(structure.get("_source_candidate_id", "")) or None,
            source_adapter=self.manifest.name,
        )

    # -- staged validators (sandboxed behind the adapter) --------------------

    def _validate_internal(self, candidate: Candidate, seed: int) -> tuple[Evidence, ...]:
        times, _, y, masked = self._curve()
        measured = _transit.fold_measure(
            times,
            y,
            float(candidate.parameters["period"]),
            float(candidate.parameters["phase_center"]),
            float(candidate.parameters["q"]),
        )
        snr = float(measured["snr"])
        return (
            Evidence(
                _identifier(candidate.candidate_id, "internal", seed),
                candidate.candidate_id,
                "internal",
                snr >= INTERNAL_SNR_THRESHOLD,
                "kepler-bls-fold-v1",
                DATASET_FULL,
                seed,
                min(1.0, snr / 50.0),
                {
                    "snr": snr,
                    "depth_ppm": measured["depth_ppm"],
                    "n_transits": measured["n_transits"],
                    "masked_rows": masked,
                    "mask_events": list(_transit.MASK_EVENTS),
                    "deterministic": True,
                },
            ),
        )

    def _validate_replication(
        self, candidate: Candidate, seed: int, context: ExecutionContext
    ) -> tuple[Evidence, ...]:
        """Independent halves must each re-detect the signal at the same period."""
        times, _, y, masked = self._curve()
        period = float(candidate.parameters["period"])
        mid = len(times) // 2
        halves = {"half-a": (times[:mid], y[:mid]), "half-b": (times[mid:], y[mid:])}
        details: dict[str, object] = {"masked_rows": masked}
        snrs: list[float] = []
        ok = True
        for label, (t_half, y_half) in halves.items():
            context.checkpoint()
            search = _transit.bls(
                t_half,
                y_half,
                pmin=period * (1 - 0.1),
                pmax=period * (1 + 0.1),
                nfreq=400,
                refine=False,
            )
            measured = _transit.fold_measure(
                t_half, y_half, search["period_days"], search["phase_center"], search["q"]
            )
            period_match = (
                abs(search["period_days"] - period) / period <= REPLICATION_PERIOD_TOLERANCE
            )
            half_ok = bool(measured["snr"] >= REPLICATION_SNR_THRESHOLD and period_match)
            ok = ok and half_ok
            snrs.append(float(measured["snr"]))
            details[label] = {
                "period_days": search["period_days"],
                "snr": measured["snr"],
                "period_match": period_match,
                "passed": half_ok,
            }
        score = min(1.0, min(snrs) / 20.0) if snrs else 0.0
        return (
            Evidence(
                _identifier(candidate.candidate_id, "replication", seed),
                candidate.candidate_id,
                "replication",
                ok,
                "kepler-half-replication-v1",
                DATASET_HALVES,
                seed,
                score,
                details,
            ),
        )

    def _validate_review(
        self, candidate: Candidate, seed: int, context: ExecutionContext
    ) -> tuple[Evidence, ...]:
        """Adversarial checks: odd/even depth, secondary eclipse, harmonics."""
        times, _, y, _ = self._curve()
        period = float(candidate.parameters["period"])
        measured = _transit.fold_measure(
            times,
            y,
            period,
            float(candidate.parameters["phase_center"]),
            float(candidate.parameters["q"]),
        )
        context.checkpoint()
        harmonics = _transit.harmonic_powers(times, y, period)
        odd_even_sigma = abs(float(measured["odd_even"]["delta_sigma"]))
        secondary_sigma = float(measured["secondary"]["sigma"])
        odd_even_ok = odd_even_sigma < REVIEW_ODD_EVEN_SIGMA
        secondary_ok = secondary_sigma < REVIEW_SECONDARY_SIGMA
        harmonic_ok = harmonics["fundamental"]["power"] >= harmonics["half"]["power"]
        passed = bool(odd_even_ok and secondary_ok and harmonic_ok)
        return (
            Evidence(
                _identifier(candidate.candidate_id, "review", seed),
                candidate.candidate_id,
                "review",
                passed,
                "kepler-adversarial-review-v1",
                DATASET_REVIEW,
                seed,
                None,
                {
                    "odd_even_delta_sigma": odd_even_sigma,
                    "odd_even_ok": odd_even_ok,
                    "secondary_sigma": secondary_sigma,
                    "secondary_ok": secondary_ok,
                    "harmonic_fundamental_power": harmonics["fundamental"]["power"],
                    "harmonic_half_power": harmonics["half"]["power"],
                    "harmonic_ok": harmonic_ok,
                },
            ),
        )
