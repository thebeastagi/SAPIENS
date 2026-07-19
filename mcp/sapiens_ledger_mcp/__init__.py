"""SAPIENS LEDGER MCP server — read-only, offline, zero-dependency.

Exposes the committed LEDGER-demo artifacts (demos/ledger-grok/) over the
Model Context Protocol (stdio transport) as three read-only tools:

  - ledger_verify    verify the hash-chained ledger + data sha256
  - ledger_query     sanitized view of ledger entries / results.json
  - transit_redetect re-run the bounded Kepler-10 b detection (deterministic)

No write tools, no model/API calls, no network, no credentials.
"""

__version__ = "0.1.0"
SERVER_NAME = "sapiens-ledger-mcp"
