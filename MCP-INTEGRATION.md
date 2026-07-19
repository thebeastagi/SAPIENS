# MCP Integration — SAPIENS LEDGER demo (Grok CLI and other MCP clients)

This repository ships a small, **read-only, offline, zero-dependency** MCP
server exposing the LEDGER demo (`demos/ledger-grok/`) to any MCP client over
stdio. It lets an agent (e.g. Grok CLI) verify the evidence ledger, inspect
sanitized ledger/results fields, and deterministically re-run the bounded
Kepler-10 b transit detection — without any credentials, network access, or
write capability.

The server is a Python 3.10+ standard-library-only implementation of the MCP
stdio transport (newline-delimited JSON-RPC 2.0). There is nothing to install
beyond the repo checkout itself.

## Tools

| Tool | What it does | Deterministic | Offline |
|---|---|---|---|
| `ledger_verify` | Recomputes every SHA-256 link of `demos/ledger-grok/out/ledger.jsonl` and checks the data file's sha256 against the `data_ingested` entry. Returns pass/fail, entry count/kinds, and the chain head hash. | yes | yes |
| `ledger_query` | Returns sanitized entries from the committed ledger (`source="ledger"`, with `kind`/`limit`/`offset` filters) or fields from `out/results.json` (`source="results"`, optional `section`). Sensitive-looking keys are redacted and long strings truncated. | yes | yes |
| `transit_redetect` | Re-runs the bounded detection on the committed sample CSV: running-median detrend + box-least-squares, then compares against the published Kepler-10 b ephemeris. Default grid (`nfreq=6000` + refine) reproduces the committed analysis **exactly**; runtime is bounded (~25 s worst case, `nfreq` capped at 6000). | yes | yes |

There are intentionally **no write tools, no model/API calls, and no network
access**. No tool accepts a filesystem path, so there is no path-traversal
surface; the only inputs are enum strings, integers, and booleans.

## Run it manually (smoke test)

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"you","version":"0"}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | python3 mcp/sapiens_ledger_mcp/server.py
```

## Grok CLI configuration

Custom MCP connectors in Grok CLI are **per-user installs** — there is no
public catalog; each user registers the server in their own settings (verified
against the Grok CLI docs). Global settings live in
`~/.grok/user-settings.json`; project-level settings in `.grok/settings.json`.

### Option A — CLI (recommended)

```bash
grok mcp add sapiens-ledger \
  -t stdio \
  -c python3 \
  -a /absolute/path/to/SAPIENS/mcp/sapiens_ledger_mcp/server.py

grok mcp list                 # confirm registration
grok mcp test sapiens-ledger  # confirm handshake + tools
```

### Option B — raw JSON

```bash
grok mcp add-json sapiens-ledger '{
  "transport": {
    "type": "stdio",
    "command": "python3",
    "args": ["/absolute/path/to/SAPIENS/mcp/sapiens_ledger_mcp/server.py"]
  }
}'
```

### Option C — settings file

Add to `~/.grok/user-settings.json` (global) or `.grok/settings.json`
(project), merging with any existing `mcpServers` array:

```json
{
  "mcpServers": [
    {
      "name": "sapiens-ledger",
      "transport": {
        "type": "stdio",
        "command": "python3",
        "args": ["/absolute/path/to/SAPIENS/mcp/sapiens_ledger_mcp/server.py"]
      }
    }
  ]
}
```

No `env` block is needed: the server reads **no** environment variables and
uses **no** API keys. Do not add `GROK_API_KEY`/`XAI_API_KEY` here — the demo
adapter's live mode is not part of the MCP surface.

### Other MCP clients

Any stdio MCP client can use the same server with the standard
`{"mcpServers": {"sapiens-ledger": {"command": "python3", "args":
["/absolute/path/to/SAPIENS/mcp/sapiens_ledger_mcp/server.py"]}}}` shape.

## Security posture

- **Read-only**: the tool allowlist is fixed at three tools; nothing writes to
  disk, spawns processes, or mutates state.
- **Offline**: no sockets, no HTTP, no model/API calls. Works air-gapped.
- **Zero credentials**: no environment variables are read; the committed
  artifacts contain no secrets (the sanitiser in `ledger_query` additionally
  redacts any key whose name contains token/secret/password/api_key/
  authorization, defence-in-depth).
- **No injection surface**: tools accept no filesystem paths and no free-form
  code; inputs are JSON-Schema-validated enums/integers/booleans, and tool
  arguments are re-validated in the dispatch layer.
- **Bounded compute**: `transit_redetect` caps `nfreq` at 6000 (~25 s) and
  `ledger_query` caps page size at 100 entries and string length at 1000
  chars.
- **Verifiable**: the same ledger the tools serve is independently checkable
  with `python3 demos/ledger-grok/verify_ledger.py`.

## Tests

`mcp/tests/` contains offline, deterministic unit tests for all three tools
plus protocol tests (initialize negotiation, tools/list, tools/call,
notifications, error codes, and an end-to-end stdio subprocess run). They run
as part of the repo's normal `pytest` suite — no extra configuration.
