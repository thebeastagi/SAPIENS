#!/usr/bin/env python3
"""MCP stdio server for the SAPIENS LEDGER demo (read-only, offline, zero-dep).

Speaks the Model Context Protocol over stdio: newline-delimited JSON-RPC 2.0
messages on stdin/stdout, per the MCP stdio transport specification. No third
-party dependencies — Python 3.10+ standard library only.

Run directly (recommended for MCP client configs):

    python3 /path/to/SAPIENS/mcp/sapiens_ledger_mcp/server.py

or as a module from the repo root:

    PYTHONPATH=mcp python3 -m sapiens_ledger_mcp.server

The server is read-only: it exposes exactly three tools (ledger_verify,
ledger_query, transit_redetect), accepts no filesystem paths, performs no
network or model/API calls, reads no environment variables or credentials,
and writes nothing to disk. All output on stdout is protocol JSON; diagnostics
never mix with the transport.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # direct `python3 path/to/server.py` invocation
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sapiens_ledger_mcp import SERVER_NAME, __version__
    from sapiens_ledger_mcp.tools import TOOL_DEFINITIONS, TOOL_FUNCTIONS
else:
    from . import SERVER_NAME, __version__
    from .tools import TOOL_DEFINITIONS, TOOL_FUNCTIONS

# Protocol revisions this server can speak. The server echoes the client's
# requested version when supported, otherwise offers its newest.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2024-11-05")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

INSTRUCTIONS = (
    "Read-only, offline access to the SAPIENS LEDGER demo (Kepler-10 b "
    "re-derivation with a hash-chained evidence ledger). Tools: ledger_verify "
    "(chain integrity + data hash), ledger_query (sanitized ledger/results "
    "fields), transit_redetect (deterministic re-run of the bounded detection). "
    "This is a validation demo — no discovery is claimed."
)

# JSON-RPC 2.0 error codes.
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602


def _result(request_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _tool_result(request_id: Any, payload: Any, *, is_error: bool = False) -> dict:
    return _result(
        request_id,
        {
            "content": [{"type": "text", "text": json.dumps(payload, indent=2, sort_keys=True)}],
            "isError": is_error,
        },
    )


def _handle_initialize(request_id: Any, params: dict) -> dict:
    requested = (params or {}).get("protocolVersion", LATEST_PROTOCOL_VERSION)
    negotiated = (
        requested if requested in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
    )
    return _result(
        request_id,
        {
            "protocolVersion": negotiated,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": __version__},
            "instructions": INSTRUCTIONS,
        },
    )


def _handle_tools_call(request_id: Any, params: Any) -> dict:
    if not isinstance(params, dict) or "name" not in params:
        return _error(request_id, _INVALID_PARAMS, "tools/call requires params.name")
    name = params["name"]
    arguments = params.get("arguments") or {}
    if name not in TOOL_FUNCTIONS:
        return _error(request_id, _INVALID_PARAMS, f"unknown tool: {name!r}")
    if not isinstance(arguments, dict):
        return _error(request_id, _INVALID_PARAMS, "params.arguments must be an object")
    try:
        payload = TOOL_FUNCTIONS[name](**arguments)
    except TypeError as exc:  # unexpected argument names/types
        return _error(request_id, _INVALID_PARAMS, f"invalid arguments for {name}: {exc}")
    except Exception as exc:  # tool execution failed -> tool-level error result
        return _tool_result(
            request_id, {"error": f"{type(exc).__name__}: {exc}"}, is_error=True
        )
    is_error = isinstance(payload, dict) and "error" in payload and name != "ledger_verify"
    return _tool_result(request_id, payload, is_error=is_error)


def handle_message(message: Any) -> dict | None:
    """Handle one JSON-RPC message; return the response (None for notifications)."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, _INVALID_REQUEST, "expected a JSON-RPC 2.0 object")
    method = message.get("method")
    request_id = message.get("id")  # absent (or null) on notifications
    is_notification = "id" not in message
    if not isinstance(method, str):
        return _error(request_id, _INVALID_REQUEST, "missing method")
    if method.startswith("notifications/"):
        return None  # e.g. notifications/initialized — never answered
    if method == "initialize":
        return _handle_initialize(request_id, message.get("params") or {})
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": TOOL_DEFINITIONS})
    if method == "tools/call":
        return _handle_tools_call(request_id, message.get("params"))
    if is_notification:
        return None
    return _error(request_id, _METHOD_NOT_FOUND, f"unknown method: {method!r}")


def serve(stdin=None, stdout=None) -> int:
    """Stdio transport loop: newline-delimited JSON-RPC messages."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout

    def _send(response: dict | None) -> None:
        if response is None:
            return
        stdout.write(json.dumps(response) + "\n")
        stdout.flush()

    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            _send(_error(None, _PARSE_ERROR, f"parse error: {exc}"))
            continue
        if isinstance(message, list):  # JSON-RPC batch
            _send([r for m in message if (r := handle_message(m)) is not None] or None)
        else:
            _send(handle_message(message))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(serve())
