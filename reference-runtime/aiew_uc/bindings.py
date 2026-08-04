# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .errors import AUECError
from .runtime import UniversalRuntime

MCP_EXTENSION_ID = "org.aiew.auec"
A2A_EXTENSION_URI = "https://aiew.example/spec/extensions/auec/0.1"
MEDIA_TYPE = "application/vnd.aiew.auec+json"


def mcp_tool_descriptor() -> dict[str, Any]:
    return {
        "name": "aiew.execute_manifest",
        "title": "Execute an AIEW Universal Execution Contract manifest",
        "description": "Validates and executes a transport-neutral AUEC U0 manifest under host policy.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["manifest"],
            "properties": {"manifest": {"type": "object"}},
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
    }


def handle_mcp_tool_call(runtime: UniversalRuntime, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name != "aiew.execute_manifest" or set(arguments) != {"manifest"} or not isinstance(arguments["manifest"], dict):
        raise AUECError("E_MCP", "invalid AUEC MCP tool call")
    result = runtime.execute(arguments["manifest"])
    return {
        "content": [{"type": "text", "text": "AUEC execution completed"}],
        "structuredContent": result,
        "isError": result.get("status") != "succeeded",
        "_meta": {"aiew/mediaType": MEDIA_TYPE, "aiew/extension": MCP_EXTENSION_ID},
    }


def a2a_task_artifact(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": "auec-result",
        "description": "AIEW Universal Execution Contract result",
        "parts": [{"data": deepcopy(result), "mediaType": MEDIA_TYPE}],
        "metadata": {"extensions": [{"uri": A2A_EXTENSION_URI, "required": True}]},
    }


def http_response(result: dict[str, Any]) -> tuple[int, dict[str, str], dict[str, Any]]:
    status = 200 if result.get("status") == "succeeded" else 422
    return status, {"content-type": MEDIA_TYPE}, deepcopy(result)
