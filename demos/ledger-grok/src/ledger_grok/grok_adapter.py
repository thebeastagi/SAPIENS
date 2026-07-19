"""Grok adapter: hypothesis-generation + adversarial-challenge layer.

Two implementations behind one small interface:

* ``MockGrokAdapter`` — deterministic, offline, credential-free stand-in.
  This is the shipped demo path: tests and the committed demo run use it, so
  the whole pipeline is reproducible with zero network and zero secrets.
  Its outputs are fixed templates seeded by the dataset hash, clearly
  labelled as mock output wherever they appear.

* ``RealGrokAdapter`` — calls the xAI chat-completions API with
  ``GROK_API_KEY`` read from the environment. The key is never written to
  the ledger, results, logs, or any other artifact. The fleet environment
  currently has no xAI key configured, so this path is documented as
  ready-to-run but was not exercised for the committed demo run.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.request

HYPOTHESIS_SCHEMA_HINT = (
    '{"text": str, "predicted_period_range_days": [lo, hi], '
    '"predicted_depth_ppm_range": [lo, hi], "predicted_duration_hours_range": [lo, hi], '
    '"shape": str, "rationale": str}'
)
CHALLENGE_SCHEMA_HINT = (
    '{"challenges": [{"id": str, "question": str, "severity": "high"|"medium"|"low", '
    '"suggested_check": str}], "overall_skepticism": str}'
)


class MockGrokAdapter:
    """Deterministic offline stand-in for Grok (seeded by the dataset hash)."""

    name = "grok-mock (deterministic offline stand-in)"

    def __init__(self, seed: int) -> None:
        self.seed = seed

    @classmethod
    def from_data_hash(cls, data_sha256: str) -> "MockGrokAdapter":
        return cls(int(data_sha256[:16], 16))

    def generate_hypothesis(self, context: dict) -> dict:
        tag = hashlib.sha256(f"hyp:{self.seed}".encode()).hexdigest()[:8]
        return {
            "adapter": "mock",
            "hypothesis_id": f"mock-hyp-{tag}",
            "text": (
                "The light curve contains a repeating, shallow, box-like dimming: "
                "a planetary-transit candidate. Expect a short period, a depth of "
                "tens-to-hundreds of ppm, and a duration of a few hours."
            ),
            "predicted_period_range_days": [0.5, 10.0],
            "predicted_depth_ppm_range": [20, 2000],
            "predicted_duration_hours_range": [0.5, 8.0],
            "shape": "box (flat-bottomed transit)",
            "rationale": (
                "Deterministic mock prior derived from dataset summary statistics "
                f"(rows={context.get('rows')}, span_days={context.get('span_days')}); "
                "a live Grok adapter would reason over the same context."
            ),
        }

    def adversarial_challenge(self, findings: dict) -> dict:
        return {
            "adapter": "mock",
            "challenges": [
                {
                    "id": "harmonic_confusion",
                    "question": (
                        "Is the detected period the true period or a harmonic? "
                        "Compare box power at P/2, P and 2P."
                    ),
                    "severity": "high",
                    "suggested_check": "harmonic_powers",
                },
                {
                    "id": "odd_even_depth",
                    "question": (
                        "Do odd- and even-numbered transits differ in depth? "
                        "A significant difference flags an eclipsing binary whose "
                        "true period is 2P."
                    ),
                    "severity": "high",
                    "suggested_check": "odd_even_fold",
                },
                {
                    "id": "secondary_eclipse",
                    "question": (
                        "Is there a secondary dip near phase 0.5? A deep secondary "
                        "flags a self-luminous companion rather than a planet."
                    ),
                    "severity": "medium",
                    "suggested_check": "secondary_fold",
                },
            ],
            "overall_skepticism": (
                "Deterministic mock challenge set (standard false-positive screen "
                "for transit candidates); not a live model output."
            ),
        }


class RealGrokAdapter:
    """Live xAI Grok adapter. Requires GROK_API_KEY in the environment."""

    name = "grok (xAI API, live)"
    API_URL = "https://api.x.ai/v1/chat/completions"

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 60):
        self.api_key = api_key or os.environ.get("GROK_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "GROK_API_KEY is not set — run with the mock adapter (offline, default) "
                "or export a key to use the live Grok path."
            )
        self.model = model or os.environ.get("GROK_MODEL", "grok-4")
        self.timeout = timeout

    def _chat(self, system: str, user: str) -> dict:
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.API_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):  # strip code fences if the model adds them
            content = content.strip("`").removeprefix("json").strip()
        return json.loads(content)

    def generate_hypothesis(self, context: dict) -> dict:
        result = self._chat(
            "You are Grok acting as the hypothesis-generation layer inside the "
            "SAPIENS evidence-ledger pipeline. Respond with strict JSON only, "
            f"matching this shape: {HYPOTHESIS_SCHEMA_HINT}",
            "Dataset summary for an astronomical light curve (BKJD time series):\n"
            + json.dumps(context, indent=2, sort_keys=True),
        )
        result["adapter"] = "xai-live"
        result["model"] = self.model
        return result

    def adversarial_challenge(self, findings: dict) -> dict:
        result = self._chat(
            "You are Grok acting as the adversarial-review layer inside the "
            "SAPIENS evidence-ledger pipeline. Attack this transit detection: "
            "propose concrete false-positive checks. Respond with strict JSON "
            f"only, matching this shape: {CHALLENGE_SCHEMA_HINT}",
            "Detection findings:\n" + json.dumps(findings, indent=2, sort_keys=True),
        )
        result["adapter"] = "xai-live"
        result["model"] = self.model
        return result


def get_adapter(name: str, data_sha256: str):
    """Factory: 'mock' (default, offline) or 'real' (needs GROK_API_KEY)."""
    if name == "mock":
        return MockGrokAdapter.from_data_hash(data_sha256)
    if name == "real":
        return RealGrokAdapter()
    raise ValueError(f"unknown adapter: {name!r} (expected 'mock' or 'real')")
