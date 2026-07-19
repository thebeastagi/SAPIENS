"""Protocol tests for the stdio MCP server (offline, deterministic)."""

import json
import subprocess
import sys
from pathlib import Path

from sapiens_ledger_mcp import SERVER_NAME, server

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "0"},
    },
}


def test_initialize_negotiates_protocol():
    resp = server.handle_message(INIT)
    assert resp["id"] == 1
    assert resp["result"]["protocolVersion"] == "2025-06-18"
    assert resp["result"]["serverInfo"]["name"] == SERVER_NAME
    assert "tools" in resp["result"]["capabilities"]
    old = dict(INIT, params={**INIT["params"], "protocolVersion": "1999-01-01"})
    resp = server.handle_message(old)
    assert resp["result"]["protocolVersion"] == server.LATEST_PROTOCOL_VERSION


def test_tools_list_advertises_exactly_three_read_only_tools():
    resp = server.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = resp["result"]["tools"]
    assert [t["name"] for t in tools] == ["ledger_verify", "ledger_query", "transit_redetect"]
    for tool in tools:  # JSON Schema present and closed
        assert tool["inputSchema"]["type"] == "object"
        assert tool["inputSchema"]["additionalProperties"] is False


def test_notifications_get_no_response():
    assert server.handle_message({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert server.handle_message({"jsonrpc": "2.0", "method": "notifications/cancelled"}) is None


def test_unknown_method_and_unknown_tool_errors():
    resp = server.handle_message({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
    assert resp["error"]["code"] == -32601
    resp = server.handle_message(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "delete_everything"}}
    )
    assert resp["error"]["code"] == -32602
    assert "unknown tool" in resp["error"]["message"]


def test_ping_and_invalid_request():
    assert server.handle_message({"jsonrpc": "2.0", "id": 5, "method": "ping"})["result"] == {}
    assert server.handle_message({"id": 6})["error"]["code"] == -32600
    assert server.handle_message(["not", "a", "dict"])["error"]["code"] == -32600


def test_tools_call_ledger_verify_over_rpc():
    resp = server.handle_message(
        {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "ledger_verify"}}
    )
    assert resp["result"]["isError"] is False
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["ok"] is True and payload["data_match"] is True


def test_tools_call_ledger_query_over_rpc():
    resp = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "ledger_query", "arguments": {"kind": "verdict"}},
        }
    )
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["total"] == 1
    assert payload["entries"][0]["kind"] == "verdict"


def test_tools_call_transit_redetect_fast_grid_over_rpc():
    resp = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "transit_redetect", "arguments": {"nfreq": 600}},
        }
    )
    payload = json.loads(resp["result"]["content"][0]["text"])
    assert payload["comparison"]["period_match"] is True
    assert payload["analysis"]["n_transits"] == 40


def test_tools_call_invalid_arguments():
    resp = server.handle_message(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "ledger_query", "arguments": {"bogus_arg": 1}},
        }
    )
    assert resp["error"]["code"] == -32602


def test_end_to_end_over_real_stdio_subprocess():
    server_py = (
        Path(__file__).resolve().parents[1] / "sapiens_ledger_mcp" / "server.py"
    )
    lines = [
        json.dumps(INIT),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "ledger_verify"},
            }
        ),
        "this is not json",
    ]
    proc = subprocess.run(
        [sys.executable, str(server_py)],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    replies = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert len(replies) == 4  # notification answered with nothing
    assert replies[0]["result"]["serverInfo"]["name"] == SERVER_NAME
    assert len(replies[1]["result"]["tools"]) == 3
    payload = json.loads(replies[2]["result"]["content"][0]["text"])
    assert payload["ok"] is True
    assert replies[3]["error"]["code"] == -32700
