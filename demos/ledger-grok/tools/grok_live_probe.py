#!/usr/bin/env python3
"""Bounded one-call live-adapter proof for the SAPIENS LEDGER demo.

Makes exactly ONE minimal xAI chat-completions call to prove the live Grok
adapter path works end to end. The API key is read from the environment only
(XAI_API_KEY, falling back to GROK_API_KEY) and is never printed, logged, or
copied into any artifact. Only model, HTTP status, usage, latency, and the
sanitized text reply are recorded. The deterministic offline mock adapter
remains the default and reproducible path for the demo.

Usage:
    python tools/grok_live_probe.py [out/grok-live-probe.json]
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API_URL = "https://api.x.ai/v1/chat/completions"
PROMPT = (
    "In one sentence, state an adversarial-review question you would ask about a "
    "claimed re-detection of the known exoplanet Kepler-10 b in a light-curve "
    "validation demo. Reply with that single sentence only."
)


def main(argv: list[str]) -> int:
    key = os.environ.get("XAI_API_KEY") or os.environ.get("GROK_API_KEY")
    if not key:
        print("no XAI_API_KEY/GROK_API_KEY in environment; live probe skipped", file=sys.stderr)
        return 2
    model = os.environ.get("GROK_MODEL", "grok-4.20-0309-non-reasoning")
    body = json.dumps(
        {
            "model": model,
            "temperature": 0,
            "max_tokens": 96,
            "messages": [{"role": "user", "content": PROMPT}],
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            status = response.status
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # deliberately do NOT print the response body
        print(f"live probe failed: HTTP {exc.code} (body suppressed)", file=sys.stderr)
        return 1
    latency = round(time.time() - started, 2)

    usage = data.get("usage", {})
    probe = {
        "kind": "bounded_live_adapter_probe",
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "endpoint": API_URL,
        "model": model,
        "http_status": status,
        "latency_s": latency,
        "max_tokens": 96,
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        },
        "cost_note": "xAI response carries no cost field; single minimal-token call",
        "prompt": PROMPT,
        "reply_text": data["choices"][0]["message"]["content"].strip(),
        "sanitization": (
            "API key read from environment only; never printed, logged, or copied; "
            "this file intentionally contains no credentials"
        ),
        "note": (
            "one-call proof only; the committed demo ledger and tests use the "
            "deterministic offline mock adapter"
        ),
    }
    out = Path(argv[1] if len(argv) > 1 else "out/grok-live-probe.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(probe, indent=2) + "\n", encoding="utf-8")
    print(
        f"live probe OK: HTTP {status}, model={model}, "
        f"total_tokens={usage.get('total_tokens')} -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
