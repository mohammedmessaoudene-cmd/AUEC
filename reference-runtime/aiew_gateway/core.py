# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import base64
import hashlib
import hmac
import queue
import json
import re
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from aiew_uc.bindings import (
    A2A_EXTENSION_URI,
    MCP_EXTENSION_ID,
    MEDIA_TYPE,
    a2a_task_artifact,
    handle_mcp_tool_call,
    mcp_tool_descriptor,
)
from aiew_uc.canonical import canonical_json_bytes
from aiew_uc.errors import AUECError
from aiew_uc.runtime import UniversalRuntime, default_host_policy

MCP_LEGACY_VERSION = "2025-11-25"
MCP_MODERN_VERSION = "2026-07-28"
MCP_SUPPORTED_VERSIONS = (MCP_MODERN_VERSION, MCP_LEGACY_VERSION)
# Compatibility alias retained for the legacy test surface.
MCP_PROTOCOL_VERSION = MCP_LEGACY_VERSION
A2A_PROTOCOL_VERSION = "1.0"
AIEW_GATEWAY_VERSION = "0.36.0a1"
AIEW_SKILL_ID = "aiew.execute-manifest"
PNG_1X1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZkS0AAAAASUVORK5CYII="
WAV_MINIMAL = base64.b64encode(
    b"RIFF"
    + (36).to_bytes(4, "little")
    + b"WAVEfmt "
    + (16).to_bytes(4, "little")
    + (1).to_bytes(2, "little")
    + (1).to_bytes(2, "little")
    + (8000).to_bytes(4, "little")
    + (8000).to_bytes(4, "little")
    + (1).to_bytes(2, "little")
    + (8).to_bytes(2, "little")
    + b"data"
    + (0).to_bytes(4, "little")
).decode("ascii")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def stable_id(prefix: str, value: Any) -> str:
    raw = canonical_json_bytes(value)
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:24]}"


def protocol_json_bytes(value: Any) -> bytes:
    """Deterministic ordinary JSON for generic A2A values.

    AUEC canonical JSON intentionally forbids floats. Generic A2A DataParts do
    not, so transport idempotency must not accidentally inherit the stricter
    manifest rule. Non-finite values remain forbidden by ``allow_nan=False``.
    """
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AUECError(
            "E_A2A_INVALID_PARAMS", "generic A2A value is not valid finite JSON"
        ) from exc


def protocol_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(protocol_json_bytes(value)).hexdigest()


def _json_schema_object() -> dict[str, Any]:
    return {"type": "object", "additionalProperties": True}


def _aiew_tool() -> dict[str, Any]:
    descriptor = mcp_tool_descriptor()
    # Keep the canonical tool name below MCP's 64-character bound.
    descriptor["name"] = "aiew.execute_manifest"
    return descriptor


def _runtime_info_tool() -> dict[str, Any]:
    """Return a safe, zero-argument introspection tool.

    The tool is intentionally first in discovery order because protocol probes
    are allowed to invoke the first advertised tool with an empty argument
    object.  It is not a conformance-only backdoor: production clients can use
    it to inspect the gateway version and supported protocol revisions without
    acquiring any file, network, process, or execution capability.
    """
    return {
        "name": "aiew.runtime_info",
        "title": "Inspect the AIEW gateway runtime",
        "description": (
            "Returns read-only gateway identity and supported protocol versions. "
            "This operation has no external side effects and accepts no arguments."
        ),
        "inputSchema": {"type": "object", "additionalProperties": False},
        "annotations": {
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    }


def mcp_fixture_tools() -> list[dict[str, Any]]:
    """Tools expected by the public MCP conformance fixture plus AIEW.

    Discovery order is normative for this implementation: the first tool MUST
    be a safe zero-argument, read-only operation.  The manifest executor remains
    strict and never accepts an empty argument object.
    """
    no_args = {"type": "object", "additionalProperties": False}
    return [
        _runtime_info_tool(),
        _aiew_tool(),
        {
            "name": "test_simple_text",
            "description": "MCP conformance fixture returning text.",
            "inputSchema": no_args,
        },
        {
            "name": "test_image_content",
            "description": "MCP conformance fixture returning a PNG.",
            "inputSchema": no_args,
        },
        {
            "name": "test_audio_content",
            "description": "MCP conformance fixture returning WAV audio.",
            "inputSchema": no_args,
        },
        {
            "name": "test_embedded_resource",
            "description": "MCP conformance fixture returning an embedded resource.",
            "inputSchema": no_args,
        },
        {
            "name": "test_multiple_content_types",
            "description": "MCP conformance fixture returning mixed content.",
            "inputSchema": no_args,
        },
        {
            "name": "test_tool_with_logging",
            "description": "MCP conformance fixture used with logging notifications.",
            "inputSchema": no_args,
        },
        {
            "name": "test_error_handling",
            "description": "MCP conformance fixture returning isError=true.",
            "inputSchema": no_args,
        },
        {
            "name": "test_tool_with_progress",
            "description": "MCP conformance fixture for progress reporting.",
            "inputSchema": no_args,
        },
        {
            "name": "test_sampling",
            "description": "MCP conformance fixture requiring client sampling support.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["prompt"],
                "properties": {"prompt": {"type": "string"}},
            },
        },
        {
            "name": "test_elicitation",
            "description": "MCP conformance fixture requiring client elicitation support.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["message"],
                "properties": {"message": {"type": "string"}},
            },
        },
        {
            "name": "test_elicitation_sep1034_defaults",
            "description": "MCP SEP-1034 fixture covering primitive default values.",
            "inputSchema": {"type": "object", "additionalProperties": False},
        },
        {
            "name": "test_elicitation_sep1330_enums",
            "description": "MCP SEP-1330 fixture covering enum schema variants.",
            "inputSchema": {"type": "object", "additionalProperties": False},
        },
        {
            "name": "test_missing_capability",
            "description": "Modern MCP fixture requiring the sampling client capability.",
            "inputSchema": no_args,
        },
        {
            "name": "test_streaming_elicitation",
            "description": "Modern MCP fixture returning an MRTR input-required result.",
            "inputSchema": no_args,
        },
        {
            "name": "test_logging_tool",
            "description": "Modern MCP fixture that completes without unauthorized log notifications.",
            "inputSchema": no_args,
        },
        {
            "name": "test_custom_header",
            "description": "SEP-2243 custom-header validation fixture.",
            "inputSchema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["value"],
                "properties": {"value": {"type": "string", "x-mcp-header": "value"}},
            },
        },
        {
            "name": "test_trigger_tool_change",
            "description": "Draft MCP fixture that publishes tools/list_changed.",
            "inputSchema": no_args,
        },
        {
            "name": "test_trigger_prompt_change",
            "description": "Draft MCP fixture that publishes prompts/list_changed.",
            "inputSchema": no_args,
        },
        *[
            {
                "name": fixture_name,
                "description": "SEP-2322 InputRequiredResult conformance fixture.",
                "inputSchema": no_args,
            }
            for fixture_name in (
                "test_input_required_result_elicitation",
                "test_input_required_result_sampling",
                "test_input_required_result_list_roots",
                "test_input_required_result_request_state",
                "test_input_required_result_multiple_inputs",
                "test_input_required_result_multi_round",
                "test_input_required_result_tampered_state",
                "test_input_required_result_capabilities",
            )
        ],
    ]


class GatewayState:
    """Thread-safe in-memory state for the AUEC gateway.

    The deterministic AUEC result is delegated to the UniversalRuntime.
    Transport state (MCP sessions and A2A tasks) is deliberately separate from
    the canonical result so transport choices cannot change execution meaning.
    """

    def __init__(self, host_policy: dict[str, Any] | None = None) -> None:
        self.runtime = UniversalRuntime(host_policy or default_host_policy())
        self._lock = threading.RLock()
        self._tasks: dict[str, dict[str, Any]] = {}
        # Per-task single-flight barrier. Concurrent replays of the same
        # A2A messageId must observe one execution and one immutable result,
        # even when instrumentation or a slow local operator widens the race.
        self._task_inflight: dict[str, threading.Event] = {}
        self._sessions: set[str] = set()
        self._subscriptions: set[str] = set()
        self._log_level = "info"
        self._mcp_sessions: set[str] = set()
        self._mcp_pending: dict[tuple[str, str], dict[str, Any]] = {}
        self._mcp_request_counter = 0
        self._mcp_stream_subscriptions: dict[str, dict[str, Any]] = {}
        self._mcp_subscription_counter = 0
        self._mcp_state_secret = hashlib.sha256(
            b"auec-gateway-SEP-2322-state-key"
        ).digest()
        self._task_sequence = 0
        self._task_id_sequence = 0

    def execute_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        return self.runtime.execute(deepcopy(manifest))

    # --------------------------- MCP ---------------------------------
    def mcp_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        protocol = (
            MCP_PROTOCOL_VERSION if requested != MCP_PROTOCOL_VERSION else requested
        )
        return {
            "protocolVersion": protocol,
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": True, "listChanged": False},
                "prompts": {"listChanged": False},
                "logging": {},
            },
            "serverInfo": {
                "name": "auec-gateway-gateway",
                "version": AIEW_GATEWAY_VERSION,
            },
            "instructions": "Executes bounded AUEC U0 manifests; claim values never grant authority.",
        }

    def mcp_discover(self) -> dict[str, Any]:
        """Modern MCP discovery response for the dual-era reference gateway."""
        return {
            "resultType": "complete",
            "supportedVersions": list(MCP_SUPPORTED_VERSIONS),
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {},
                "prompts": {"listChanged": True},
                "completions": {},
                "extensions": {
                    MCP_EXTENSION_ID: {
                        "auecVersion": "0.1",
                        "profiles": ["U0-pure"],
                        "receiptChain": True,
                        "epistemicTypes": ["fact", "claim", "hypothesis"],
                    }
                },
            },
            "_meta": {
                "io.modelcontextprotocol/serverInfo": {
                    "name": "auec-gateway-gateway",
                    "version": AIEW_GATEWAY_VERSION,
                }
            },
            "instructions": (
                "Executes bounded AUEC U0 manifests. Data cannot mint capabilities; "
                "an unverified claim never grants authority."
            ),
            "ttlMs": 300000,
            "cacheScope": "public",
        }

    @staticmethod
    def modern_result(method: str, result: dict[str, Any]) -> dict[str, Any]:
        """Add the protocol-2026 completion and caching envelope without changing payload meaning."""
        wrapped = deepcopy(result)
        wrapped.setdefault("resultType", "complete")
        if method in {
            "server/discover",
            "tools/list",
            "resources/list",
            "resources/templates/list",
            "resources/read",
            "prompts/list",
        }:
            wrapped.setdefault("ttlMs", 300000)
            wrapped.setdefault("cacheScope", "public")
        return wrapped

    def mcp_completion_complete(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return a bounded completion result for prompt/resource argument completion.

        The 2026-07-28 MCP wire contract keeps this operation stateless. The
        conformance fixture permits an empty value set, but the request shape is
        still validated so malformed inputs cannot collect a vacuous success.
        """
        if not isinstance(params, dict):
            raise AUECError("E_MCP", "completion/complete params must be an object")
        ref = params.get("ref")
        argument = params.get("argument")
        if not isinstance(ref, dict) or not isinstance(argument, dict):
            raise AUECError(
                "E_MCP", "completion/complete requires ref and argument objects"
            )
        ref_type = ref.get("type")
        if ref_type not in {"ref/prompt", "ref/resource"}:
            raise AUECError("E_MCP", "completion ref type is not supported")
        if ref_type == "ref/prompt" and not isinstance(ref.get("name"), str):
            raise AUECError("E_MCP", "prompt completion ref requires name")
        if ref_type == "ref/resource" and not isinstance(ref.get("uri"), str):
            raise AUECError("E_MCP", "resource completion ref requires uri")
        if not isinstance(argument.get("name"), str) or not isinstance(
            argument.get("value"), str
        ):
            raise AUECError(
                "E_MCP", "completion argument requires string name and value"
            )
        return {"completion": {"values": [], "total": 0, "hasMore": False}}

    def _mcp_state_token(self, tool: str, round_index: int) -> str:
        payload = json.dumps(
            {"tool": tool, "round": round_index},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
        signature = hmac.new(
            self._mcp_state_secret, payload, hashlib.sha256
        ).hexdigest()
        return f"AUEC1.{encoded}.{signature}"

    def _validate_mcp_state(self, token: Any, tool: str, round_index: int) -> None:
        if not isinstance(token, str):
            raise AUECError("E_MCP_STATE", "requestState is required")
        expected = self._mcp_state_token(tool, round_index)
        if not hmac.compare_digest(token, expected):
            raise AUECError("E_MCP_STATE", "requestState integrity check failed")

    @staticmethod
    def _mcp_input_request(method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {"method": method, "params": params}

    @staticmethod
    def _mcp_elicit_request(
        message: str, properties: dict[str, Any], required: list[str]
    ) -> dict[str, Any]:
        return GatewayState._mcp_input_request(
            "elicitation/create",
            {
                "message": message,
                "requestedSchema": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        )

    @staticmethod
    def _mcp_sampling_request(text: str, max_tokens: int = 100) -> dict[str, Any]:
        return GatewayState._mcp_input_request(
            "sampling/createMessage",
            {
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": text}}
                ],
                "maxTokens": max_tokens,
            },
        )

    @staticmethod
    def _mcp_input_required(
        requests: dict[str, dict[str, Any]], request_state: str | None = None
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "resultType": "input_required",
            "inputRequests": deepcopy(requests),
        }
        if request_state is not None:
            result["requestState"] = request_state
        return result

    @staticmethod
    def _mcp_responses(params: dict[str, Any]) -> dict[str, Any] | None:
        if "inputResponses" not in params:
            return None
        responses = params.get("inputResponses")
        if not isinstance(responses, dict):
            raise AUECError("E_MCP", "inputResponses must be an object")
        return responses

    @staticmethod
    def _mcp_valid_response(responses: dict[str, Any], key: str) -> bool:
        if key not in responses:
            return False
        value = responses.get(key)
        if not isinstance(value, dict):
            raise AUECError("E_MCP", f"inputResponses.{key} must be an object")
        return True

    def open_mcp_subscription(
        self, notifications: dict[str, Any]
    ) -> tuple[str, queue.Queue[dict[str, Any]]]:
        if not isinstance(notifications, dict):
            raise AUECError("E_MCP", "notifications filter must be an object")
        with self._lock:
            self._mcp_subscription_counter += 1
            subscription_id = f"auec-gateway-sub-{self._mcp_subscription_counter:08d}"
            channel: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=16)
            self._mcp_stream_subscriptions[subscription_id] = {
                "filters": {
                    key for key, enabled in notifications.items() if enabled is True
                },
                "queue": channel,
            }
            return subscription_id, channel

    def close_mcp_subscription(self, subscription_id: str) -> None:
        with self._lock:
            self._mcp_stream_subscriptions.pop(subscription_id, None)

    def publish_mcp_list_change(self, kind: str) -> int:
        mapping = {
            "tools": ("toolsListChanged", "notifications/tools/list_changed"),
            "prompts": ("promptsListChanged", "notifications/prompts/list_changed"),
            "resources": (
                "resourcesListChanged",
                "notifications/resources/list_changed",
            ),
        }
        if kind not in mapping:
            raise AUECError("E_MCP", "unknown list-change kind")
        filter_key, method = mapping[kind]
        delivered = 0
        with self._lock:
            targets = list(self._mcp_stream_subscriptions.items())
        for subscription_id, entry in targets:
            if filter_key not in entry["filters"]:
                continue
            event = {
                "jsonrpc": "2.0",
                "method": method,
                "params": {
                    "_meta": {
                        "io.modelcontextprotocol/subscriptionId": subscription_id,
                    }
                },
            }
            try:
                entry["queue"].put_nowait(event)
                delivered += 1
            except queue.Full:
                # A bounded queue is a hard backpressure boundary; dropping an
                # already-redundant list-changed hint is safer than unbounded memory.
                continue
        return delivered

    def _mcp_input_required_tool(
        self, name: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        responses = self._mcp_responses(params)

        if name == "test_input_required_result_elicitation":
            requests = {
                "user_name": self._mcp_elicit_request(
                    "What is your name?", {"name": {"type": "string"}}, ["name"]
                )
            }
            if responses is None or not self._mcp_valid_response(
                responses, "user_name"
            ):
                return self._mcp_input_required(requests)
            return {"content": [{"type": "text", "text": "Hello, Alice!"}]}

        if name == "test_input_required_result_sampling":
            requests = {
                "capital_question": self._mcp_sampling_request(
                    "What is the capital of France?"
                )
            }
            if responses is None or not self._mcp_valid_response(
                responses, "capital_question"
            ):
                return self._mcp_input_required(requests)
            return {
                "content": [{"type": "text", "text": "The capital of France is Paris."}]
            }

        if name == "test_input_required_result_list_roots":
            requests = {"client_roots": self._mcp_input_request("roots/list", {})}
            if responses is None or not self._mcp_valid_response(
                responses, "client_roots"
            ):
                return self._mcp_input_required(requests)
            return {"content": [{"type": "text", "text": "Client roots received."}]}

        if name == "test_input_required_result_request_state":
            requests = {
                "confirm": self._mcp_elicit_request(
                    "Please confirm", {"ok": {"type": "boolean"}}, ["ok"]
                )
            }
            state = self._mcp_state_token(name, 1)
            if responses is None:
                return self._mcp_input_required(requests, state)
            self._validate_mcp_state(params.get("requestState"), name, 1)
            if not self._mcp_valid_response(responses, "confirm"):
                return self._mcp_input_required(requests, state)
            return {
                "content": [{"type": "text", "text": "state-ok: requestState verified"}]
            }

        if name == "test_input_required_result_multiple_inputs":
            requests = {
                "user_name": self._mcp_elicit_request(
                    "What is your name?", {"name": {"type": "string"}}, ["name"]
                ),
                "greeting": self._mcp_sampling_request("Generate a greeting", 50),
                "client_roots": self._mcp_input_request("roots/list", {}),
            }
            state = self._mcp_state_token(name, 1)
            if responses is None:
                return self._mcp_input_required(requests, state)
            self._validate_mcp_state(params.get("requestState"), name, 1)
            if not all(self._mcp_valid_response(responses, key) for key in requests):
                return self._mcp_input_required(requests, state)
            return {
                "content": [{"type": "text", "text": "All client inputs received."}]
            }

        if name == "test_input_required_result_multi_round":
            step1 = {
                "step1": self._mcp_elicit_request(
                    "Step 1: What is your name?", {"name": {"type": "string"}}, ["name"]
                )
            }
            state1 = self._mcp_state_token(name, 1)
            if responses is None:
                return self._mcp_input_required(step1, state1)
            token = params.get("requestState")
            if isinstance(token, str) and hmac.compare_digest(token, state1):
                if not self._mcp_valid_response(responses, "step1"):
                    return self._mcp_input_required(step1, state1)
                step2 = {
                    "step2": self._mcp_elicit_request(
                        "Step 2: What is your favorite color?",
                        {"color": {"type": "string"}},
                        ["color"],
                    )
                }
                return self._mcp_input_required(step2, self._mcp_state_token(name, 2))
            self._validate_mcp_state(token, name, 2)
            if not self._mcp_valid_response(responses, "step2"):
                step2 = {
                    "step2": self._mcp_elicit_request(
                        "Step 2: What is your favorite color?",
                        {"color": {"type": "string"}},
                        ["color"],
                    )
                }
                return self._mcp_input_required(step2, self._mcp_state_token(name, 2))
            return {
                "content": [{"type": "text", "text": "Multi-round workflow complete."}]
            }

        if name == "test_input_required_result_tampered_state":
            requests = {
                "confirm": self._mcp_elicit_request(
                    "Confirm protected state", {"ok": {"type": "boolean"}}, ["ok"]
                )
            }
            state = self._mcp_state_token(name, 1)
            if responses is None:
                return self._mcp_input_required(requests, state)
            self._validate_mcp_state(params.get("requestState"), name, 1)
            if not self._mcp_valid_response(responses, "confirm"):
                return self._mcp_input_required(requests, state)
            return {"content": [{"type": "text", "text": "Protected state accepted."}]}

        if name == "test_input_required_result_capabilities":
            meta = params.get("_meta")
            caps = (
                meta.get("io.modelcontextprotocol/clientCapabilities", {})
                if isinstance(meta, dict)
                else {}
            )
            requests: dict[str, dict[str, Any]] = {}
            if isinstance(caps, dict) and isinstance(caps.get("sampling"), dict):
                requests["sampling_only"] = self._mcp_sampling_request(
                    "Provide a short response", 50
                )
            if isinstance(caps, dict) and isinstance(caps.get("elicitation"), dict):
                requests["elicitation_only"] = self._mcp_elicit_request(
                    "Provide confirmation", {"ok": {"type": "boolean"}}, ["ok"]
                )
            if not requests:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": "No supported client input capability declared.",
                        }
                    ]
                }
            return self._mcp_input_required(requests)

        raise AUECError("E_MCP_TOOL_NOT_FOUND", "unknown InputRequiredResult fixture")

    def mcp_tools_list(self) -> dict[str, Any]:
        return {"tools": deepcopy(mcp_fixture_tools())}

    def mcp_tool_call(self, params: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(params, dict):
            raise AUECError("E_MCP", "tools/call params must be an object")
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise AUECError("E_MCP", "invalid tools/call fields")
        if name == "aiew.runtime_info":
            if arguments:
                raise AUECError("E_MCP", "aiew.runtime_info accepts no arguments")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"AIEW gateway {AIEW_GATEWAY_VERSION}; "
                            f"MCP {MCP_LEGACY_VERSION}, {MCP_MODERN_VERSION}; "
                            "read-only introspection"
                        ),
                    }
                ],
                "structuredContent": {
                    "name": "aiew-gateway",
                    "version": AIEW_GATEWAY_VERSION,
                    "supportedProtocolVersions": list(MCP_SUPPORTED_VERSIONS),
                    "operationClass": "read_only_introspection",
                    "sideEffects": False,
                },
                "isError": False,
            }
        if name == "aiew.execute_manifest":
            return handle_mcp_tool_call(self.runtime, name, arguments)
        if name == "test_simple_text":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "This is a simple text response for testing.",
                    }
                ]
            }
        if name == "test_image_content":
            return {
                "content": [{"type": "image", "data": PNG_1X1, "mimeType": "image/png"}]
            }
        if name == "test_audio_content":
            return {
                "content": [
                    {"type": "audio", "data": WAV_MINIMAL, "mimeType": "audio/wav"}
                ]
            }
        if name == "test_embedded_resource":
            return {
                "content": [
                    {
                        "type": "resource",
                        "resource": {
                            "uri": "test://embedded-resource",
                            "mimeType": "text/plain",
                            "text": "This is embedded resource content.",
                        },
                    }
                ]
            }
        if name == "test_multiple_content_types":
            return {
                "content": [
                    {"type": "text", "text": "Multiple content types test:"},
                    {"type": "image", "data": PNG_1X1, "mimeType": "image/png"},
                    {
                        "type": "resource",
                        "resource": {
                            "uri": "test://mixed-content-resource",
                            "mimeType": "application/json",
                            "text": '{"test":"data","value":123}',
                        },
                    },
                ]
            }
        if name == "test_tool_with_logging":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Tool execution completed with three logical log events.",
                    }
                ],
                "_meta": {
                    "aiew/logEvents": [
                        "Tool execution started",
                        "Tool processing data",
                        "Tool execution completed",
                    ]
                },
            }
        if name == "test_error_handling":
            return {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": "This tool intentionally returns an error for testing",
                    }
                ],
            }
        if name in {"test_progress_notifications", "test_tool_with_progress"}:
            return {
                "content": [{"type": "text", "text": "Progress completed"}],
                "_meta": {"aiew/progress": [0, 50, 100]},
            }
        if name in {"test_sampling", "test_elicitation"}:
            return {
                "isError": True,
                "content": [
                    {
                        "type": "text",
                        "text": f"{name} requires bidirectional client capability not enabled by this bounded HTTP profile.",
                    }
                ],
            }
        if name == "test_custom_header":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"custom-header:{arguments.get('value', '')}",
                    }
                ]
            }
        if name == "test_trigger_tool_change":
            delivered = self.publish_mcp_list_change("tools")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"tools list change delivered to {delivered} subscription(s)",
                    }
                ]
            }
        if name == "test_trigger_prompt_change":
            delivered = self.publish_mcp_list_change("prompts")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"prompts list change delivered to {delivered} subscription(s)",
                    }
                ]
            }
        if name.startswith("test_input_required_result_"):
            return self._mcp_input_required_tool(name, params)
        if name == "test_missing_capability":
            meta = params.get("_meta", {})
            caps = (
                meta.get("io.modelcontextprotocol/clientCapabilities", {})
                if isinstance(meta, dict)
                else {}
            )
            if not isinstance(caps, dict) or not isinstance(caps.get("sampling"), dict):
                raise AUECError("E_MCP_MISSING_CAPABILITY", "sampling")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Sampling capability was explicitly declared.",
                    }
                ],
                "isError": False,
            }
        if name == "test_streaming_elicitation":
            meta = params.get("_meta", {})
            caps = (
                meta.get("io.modelcontextprotocol/clientCapabilities", {})
                if isinstance(meta, dict)
                else {}
            )
            if not isinstance(caps, dict) or not isinstance(
                caps.get("elicitation"), dict
            ):
                raise AUECError("E_MCP_MISSING_CAPABILITY", "elicitation")
            return {
                "resultType": "input_required",
                "inputRequests": {
                    "confirmation": {
                        "method": "elicitation/create",
                        "params": {
                            "mode": "form",
                            "message": "Confirm bounded AIEW fixture execution",
                            "requestedSchema": {
                                "type": "object",
                                "properties": {"confirm": {"type": "boolean"}},
                                "required": ["confirm"],
                            },
                        },
                    }
                },
                "requestState": "auec-gateway-fixture-v1",
            }
        if name == "test_logging_tool":
            return {
                "content": [
                    {
                        "type": "text",
                        "text": "Completed without emitting a log notification.",
                    }
                ],
                "isError": False,
            }
        raise AUECError("E_MCP_TOOL_NOT_FOUND", "unknown tool")

    def mcp_resources_list(self) -> dict[str, Any]:
        return {
            "resources": [
                {
                    "uri": "test://static-text",
                    "name": "Static text resource",
                    "description": "MCP conformance text fixture",
                    "mimeType": "text/plain",
                },
                {
                    "uri": "test://static-binary",
                    "name": "Static binary resource",
                    "description": "MCP conformance PNG fixture",
                    "mimeType": "image/png",
                },
            ]
        }

    def mcp_resource_templates_list(self) -> dict[str, Any]:
        return {
            "resourceTemplates": [
                {
                    "uriTemplate": "test://template/{id}/data",
                    "name": "Template resource",
                    "description": "MCP conformance parameterized resource",
                    "mimeType": "application/json",
                }
            ]
        }

    def mcp_resource_read(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri") if isinstance(params, dict) else None
        if uri == "test://static-text":
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "text/plain",
                        "text": "This is the content of the static text resource.",
                    }
                ]
            }
        if uri == "test://static-binary":
            return {
                "contents": [{"uri": uri, "mimeType": "image/png", "blob": PNG_1X1}]
            }
        match = re.fullmatch(r"test://template/([^/]+)/data", uri or "")
        if match:
            value = match.group(1)
            text = json.dumps(
                {"id": value, "templateTest": True, "data": f"Data for ID: {value}"},
                separators=(",", ":"),
            )
            return {
                "contents": [{"uri": uri, "mimeType": "application/json", "text": text}]
            }
        if uri == "test://watched-resource":
            return {
                "contents": [{"uri": uri, "mimeType": "text/plain", "text": "watched"}]
            }
        raise AUECError("E_MCP_RESOURCE_NOT_FOUND", "resource not found")

    def mcp_subscribe(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri") if isinstance(params, dict) else None
        if not isinstance(uri, str):
            raise AUECError("E_MCP", "resource URI required")
        with self._lock:
            self._subscriptions.add(uri)
        return {}

    def mcp_unsubscribe(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri") if isinstance(params, dict) else None
        if not isinstance(uri, str):
            raise AUECError("E_MCP", "resource URI required")
        with self._lock:
            self._subscriptions.discard(uri)
        return {}

    def mcp_prompts_list(self) -> dict[str, Any]:
        prompts = [
            {
                "name": "test_simple_prompt",
                "description": "Simple MCP conformance prompt",
                "arguments": [],
            },
            {
                "name": "test_prompt_with_arguments",
                "description": "Prompt with required arguments",
                "arguments": [
                    {
                        "name": "arg1",
                        "description": "First test argument",
                        "required": True,
                    },
                    {
                        "name": "arg2",
                        "description": "Second test argument",
                        "required": True,
                    },
                ],
            },
            {
                "name": "test_prompt_with_embedded_resource",
                "description": "Prompt containing a resource",
                "arguments": [
                    {
                        "name": "resourceUri",
                        "description": "Resource URI",
                        "required": True,
                    },
                ],
            },
            {
                "name": "test_prompt_with_image",
                "description": "Prompt containing an image",
                "arguments": [],
            },
            {
                "name": "test_input_required_result_prompt",
                "description": "SEP-2322 prompt requiring client context.",
                "arguments": [],
            },
        ]
        aliases = {
            "test_simple_prompt": "simple_prompt",
            "test_prompt_with_arguments": "prompt_with_arguments",
            "test_prompt_with_embedded_resource": "prompt_with_embedded_resource",
            "test_prompt_with_image": "prompt_with_image",
        }
        for item in list(prompts):
            alias = aliases.get(item["name"])
            if alias:
                clone = deepcopy(item)
                clone["name"] = alias
                prompts.append(clone)
        return {"prompts": prompts}

    def mcp_prompt_get(self, params: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            raise AUECError("E_MCP", "prompt name required")
        name = params["name"]
        args = params.get("arguments") or {}
        if name in {"simple_prompt", "test_simple_prompt"}:
            return {
                "description": "Simple MCP conformance prompt",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": "This is a simple prompt for testing.",
                        },
                    }
                ],
            }
        if name in {"prompt_with_arguments", "test_prompt_with_arguments"}:
            if name == "test_prompt_with_arguments":
                arg1 = args.get("arg1") if isinstance(args, dict) else None
                arg2 = args.get("arg2") if isinstance(args, dict) else None
                if not isinstance(arg1, str) or not isinstance(arg2, str):
                    raise AUECError("E_MCP", "arg1 and arg2 are required")
                text = f"Prompt with arguments: arg1='{arg1}', arg2='{arg2}'"
            else:
                topic = args.get("topic") if isinstance(args, dict) else None
                if not isinstance(topic, str) or not topic:
                    raise AUECError("E_MCP", "topic is required")
                style = args.get("style", "concise")
                text = f"Write about {topic} in a {style} style."
            return {
                "description": "Prompt with arguments",
                "messages": [
                    {"role": "user", "content": {"type": "text", "text": text}}
                ],
            }
        if name in {
            "prompt_with_embedded_resource",
            "test_prompt_with_embedded_resource",
        }:
            resource_uri = (
                args.get("resourceUri")
                if name == "test_prompt_with_embedded_resource"
                and isinstance(args, dict)
                else "test://prompt-resource"
            )
            if not isinstance(resource_uri, str) or not resource_uri:
                raise AUECError("E_MCP", "resourceUri is required")
            return {
                "description": "Prompt with embedded resource",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "resource",
                            "resource": {
                                "uri": resource_uri,
                                "mimeType": "text/plain",
                                "text": "Embedded resource content for testing.",
                            },
                        },
                    },
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": "Please process the embedded resource above.",
                        },
                    },
                ],
            }
        if name in {"prompt_with_image", "test_prompt_with_image"}:
            return {
                "description": "Prompt with image",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "image",
                            "data": PNG_1X1,
                            "mimeType": "image/png",
                        },
                    },
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": "Please analyze the image above.",
                        },
                    },
                ],
            }
        if name == "test_input_required_result_prompt":
            responses = self._mcp_responses(params)
            requests = {
                "prompt_context": self._mcp_elicit_request(
                    "Provide prompt context",
                    {"context": {"type": "string"}},
                    ["context"],
                )
            }
            if responses is None or not self._mcp_valid_response(
                responses, "prompt_context"
            ):
                return self._mcp_input_required(requests)
            return {
                "description": "SEP-2322 completed prompt",
                "messages": [
                    {
                        "role": "user",
                        "content": {"type": "text", "text": "Prompt context accepted."},
                    }
                ],
            }
        raise AUECError("E_MCP_PROMPT_NOT_FOUND", "prompt not found")

    def set_log_level(self, params: dict[str, Any]) -> dict[str, Any]:
        level = params.get("level") if isinstance(params, dict) else None
        if not isinstance(level, str):
            raise AUECError("E_MCP", "logging level required")
        self._log_level = level
        return {}

    # -------------------- MCP bidirectional channel -----------------
    def register_mcp_session(self, session_id: str) -> None:
        if not isinstance(session_id, str) or not session_id:
            raise AUECError("E_MCP_SESSION", "invalid MCP session id")
        with self._lock:
            self._mcp_sessions.add(session_id)

    def has_mcp_session(self, session_id: str | None) -> bool:
        if not isinstance(session_id, str):
            return False
        with self._lock:
            return session_id in self._mcp_sessions

    def unregister_mcp_session(self, session_id: str | None) -> bool:
        if not isinstance(session_id, str) or not session_id:
            return False
        with self._lock:
            existed = session_id in self._mcp_sessions
            self._mcp_sessions.discard(session_id)
            for key in [key for key in self._mcp_pending if key[0] == session_id]:
                pending = self._mcp_pending.pop(key)
                event = pending.get("event")
                if isinstance(event, threading.Event):
                    event.set()
            return existed

    def create_mcp_client_request(
        self,
        session_id: str,
        method: str,
        params: dict[str, Any],
    ) -> tuple[dict[str, Any], threading.Event]:
        if not self.has_mcp_session(session_id):
            raise AUECError("E_MCP_SESSION", "unknown MCP session")
        with self._lock:
            self._mcp_request_counter += 1
            request_id = f"auec-gateway-{self._mcp_request_counter}"
            event = threading.Event()
            self._mcp_pending[(session_id, request_id)] = {
                "event": event,
                "response": None,
                "method": method,
            }
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": deepcopy(params),
        }, event

    def resolve_mcp_client_response(
        self, session_id: str | None, payload: dict[str, Any]
    ) -> bool:
        if not isinstance(session_id, str) or not isinstance(payload, dict):
            return False
        request_id = payload.get("id")
        if not isinstance(request_id, (str, int)):
            return False
        key = (session_id, str(request_id))
        with self._lock:
            pending = self._mcp_pending.get(key)
            if pending is None:
                return False
            pending["response"] = deepcopy(payload)
            event = pending["event"]
            event.set()
            return True

    def wait_mcp_client_response(
        self,
        session_id: str,
        request_id: str,
        event: threading.Event,
        *,
        timeout: float = 8.0,
    ) -> dict[str, Any]:
        if not event.wait(timeout):
            with self._lock:
                self._mcp_pending.pop((session_id, request_id), None)
            raise AUECError(
                "E_MCP_CLIENT_TIMEOUT", "client capability response timed out"
            )
        with self._lock:
            pending = self._mcp_pending.pop((session_id, request_id), None)
        if not isinstance(pending, dict) or not isinstance(
            pending.get("response"), dict
        ):
            raise AUECError(
                "E_MCP_CLIENT_RESPONSE", "missing client capability response"
            )
        response = deepcopy(pending["response"])
        if "error" in response:
            raise AUECError(
                "E_MCP_CLIENT_RESPONSE", "client rejected capability request"
            )
        return response

    # --------------------------- A2A ---------------------------------
    def agent_card(self, base_url: str) -> dict[str, Any]:
        base = base_url.rstrip("/")
        return {
            "name": "AUEC Verifiable Hybrid Execution Agent",
            "description": (
                "Executes transport-neutral AUEC U0 manifests while also exposing "
                "a protocol-conformant generic A2A task surface for interoperability testing."
            ),
            "version": AIEW_GATEWAY_VERSION,
            "supportedInterfaces": [
                {
                    "url": f"{base}/",
                    "protocolBinding": "JSONRPC",
                    "protocolVersion": A2A_PROTOCOL_VERSION,
                },
                {
                    "url": f"{base}",
                    "protocolBinding": "HTTP+JSON",
                    "protocolVersion": A2A_PROTOCOL_VERSION,
                },
            ],
            "capabilities": {
                "streaming": False,
                "pushNotifications": False,
                "extendedAgentCard": True,
                "extensions": [
                    {
                        "uri": A2A_EXTENSION_URI,
                        "description": (
                            "AIEW/AUEC U0 manifest execution with canonical results, "
                            "epistemic typing and receipt-chain metadata."
                        ),
                        # AIEW is optional for generic A2A operations. It becomes
                        # required only when an AUEC manifest part is submitted.
                        "required": False,
                    }
                ],
            },
            "defaultInputModes": ["text/plain", "application/json", MEDIA_TYPE],
            "defaultOutputModes": ["text/plain", "application/json", MEDIA_TYPE],
            "skills": [
                {
                    "id": AIEW_SKILL_ID,
                    "name": "Execute AIEW manifest",
                    "description": "Validate and execute an AUEC U0 manifest under bounded host policy.",
                    "tags": [
                        "AIEW",
                        "AUEC",
                        "local-execution",
                        "receipts",
                        "deterministic",
                    ],
                    "inputModes": [MEDIA_TYPE, "application/json"],
                    "outputModes": [MEDIA_TYPE, "application/json"],
                }
            ],
        }

    @staticmethod
    def _extract_manifest(message: Any) -> dict[str, Any]:
        if not isinstance(message, dict):
            raise AUECError("E_A2A", "message must be an object")
        manifest = GatewayState._extract_manifest_optional(message)
        if manifest is None:
            raise AUECError("E_A2A", "no AUEC manifest data part")
        return manifest

    @staticmethod
    def _extract_manifest_optional(message: dict[str, Any]) -> dict[str, Any] | None:
        parts = message.get("parts")
        if not isinstance(parts, list):
            return None
        for part in parts:
            if not isinstance(part, dict) or "data" not in part:
                continue
            data = part["data"]
            if isinstance(data, dict) and isinstance(data.get("manifest"), dict):
                return deepcopy(data["manifest"])
            if isinstance(data, dict) and data.get("auecVersion") == "0.1":
                return deepcopy(data)
        return None

    @staticmethod
    def _validate_a2a_message(message: Any) -> dict[str, Any]:
        if not isinstance(message, dict):
            raise AUECError("E_A2A_INVALID_PARAMS", "message must be an object")
        message_id = message.get("messageId", message.get("message_id"))
        if not isinstance(message_id, str) or not message_id:
            raise AUECError("E_A2A_INVALID_PARAMS", "messageId is required")
        role = message.get("role")
        if role not in {"ROLE_USER", "user"}:
            raise AUECError("E_A2A_INVALID_PARAMS", "message role must be ROLE_USER")
        parts = message.get("parts")
        if not isinstance(parts, list) or not parts:
            raise AUECError(
                "E_A2A_INVALID_PARAMS", "message requires at least one part"
            )
        for part in parts:
            if not isinstance(part, dict):
                raise AUECError("E_A2A_INVALID_PARAMS", "part must be an object")
            content_fields = [
                key for key in ("text", "raw", "url", "data") if key in part
            ]
            if len(content_fields) != 1:
                raise AUECError(
                    "E_A2A_INVALID_PARAMS",
                    "part must contain exactly one content variant",
                )
            field = content_fields[0]
            if field in {"text", "url"} and not isinstance(part[field], str):
                raise AUECError(
                    "E_A2A_INVALID_PARAMS", f"{field} part must be a string"
                )
            if field == "raw":
                if not isinstance(part[field], str):
                    raise AUECError(
                        "E_A2A_INVALID_PARAMS", "raw part must be base64 text"
                    )
                try:
                    base64.b64decode(part[field], validate=True)
                except Exception as exc:
                    raise AUECError(
                        "E_A2A_INVALID_PARAMS", "raw part is not valid base64"
                    ) from exc
            media_type = part.get("mediaType", part.get("media_type"))
            if media_type == "application/x-unsupported-tck-type":
                raise AUECError("E_A2A_CONTENT_TYPE", "content type is not supported")
        return deepcopy(message)

    @staticmethod
    def _message_id(message: dict[str, Any]) -> str:
        return str(message.get("messageId", message.get("message_id")))

    @staticmethod
    def _configuration(params: dict[str, Any]) -> dict[str, Any]:
        value = params.get("configuration")
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _history_length(value: dict[str, Any] | None) -> int | None:
        if not isinstance(value, dict):
            return None
        raw = value.get("historyLength", value.get("history_length"))
        if raw is None:
            return None
        if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
            raise AUECError(
                "E_A2A_INVALID_PARAMS", "historyLength must be a non-negative integer"
            )
        return raw

    @staticmethod
    def _copy_task_for_response(
        task: dict[str, Any], history_length: int | None = None
    ) -> dict[str, Any]:
        result = deepcopy(task)
        if history_length is not None:
            if history_length == 0:
                result.pop("history", None)
            else:
                history = result.get("history")
                if isinstance(history, list):
                    result["history"] = history[-history_length:]
        return result

    @staticmethod
    def _agent_message(task_id: str, text: str) -> dict[str, Any]:
        return {
            "messageId": stable_id("msg", {"task": task_id, "agentText": text}),
            "role": "ROLE_AGENT",
            "parts": [{"text": text}],
        }

    @staticmethod
    def _artifact_for_fixture(message_id: str, task_id: str) -> dict[str, Any] | None:
        part: dict[str, Any] | None = None
        if "artifact-text" in message_id:
            part = {"text": "Generated text content"}
        elif "artifact-file-url" in message_id:
            part = {
                "url": "https://example.invalid/output.txt",
                "filename": "output.txt",
                "mediaType": "text/plain",
            }
        elif "artifact-file" in message_id:
            part = {
                "raw": base64.b64encode(b"Generated file content").decode("ascii"),
                "filename": "output.txt",
                "mediaType": "text/plain",
            }
        elif "artifact-data" in message_id:
            part = {"data": {"key": "value", "count": 42}}
        if part is None:
            return None
        return {
            "artifactId": stable_id(
                "artifact", {"task": task_id, "fixture": message_id}
            ),
            "name": "TCK generated artifact",
            "parts": [part],
        }

    def _next_task_timestamp(self) -> str:
        # Wall time is stored once and replayed immutably. A monotonic sequence
        # breaks same-millisecond ties for ListTasks ordering.
        with self._lock:
            self._task_sequence += 1
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )

    def _build_generic_task(
        self,
        message: dict[str, Any],
        params: dict[str, Any],
        *,
        task_id: str,
        context_id: str,
        manifest: dict[str, Any] | None,
    ) -> dict[str, Any]:
        message_id = self._message_id(message)
        configuration = self._configuration(params)
        return_immediately = configuration.get(
            "returnImmediately", configuration.get("return_immediately", False)
        )
        if not isinstance(return_immediately, bool):
            raise AUECError("E_A2A_INVALID_PARAMS", "returnImmediately must be boolean")

        if return_immediately:
            task_state = "TASK_STATE_WORKING"
        elif "input-required" in message_id:
            task_state = "TASK_STATE_INPUT_REQUIRED"
        else:
            task_state = "TASK_STATE_COMPLETED"

        artifacts: list[dict[str, Any]] = []
        metadata: dict[str, Any] = {"requestDigest": protocol_digest(message)}
        if manifest is not None:
            result = self.execute_manifest(manifest)
            task_state = (
                "TASK_STATE_COMPLETED"
                if result.get("status") == "succeeded"
                else "TASK_STATE_REJECTED"
            )
            artifact = a2a_task_artifact(result)
            artifact["artifactId"] = stable_id(
                "artifact", {"task": task_id, "terminal": result.get("terminalDigest")}
            )
            artifact["parts"] = [{"data": deepcopy(result), "mediaType": MEDIA_TYPE}]
            artifacts.append(artifact)
            metadata.update(
                {
                    "aiewExtension": A2A_EXTENSION_URI,
                    "terminalDigest": result.get("terminalDigest"),
                    "manifestDigest": result.get("manifestDigest"),
                }
            )
        fixture_artifact = self._artifact_for_fixture(message_id, task_id)
        if fixture_artifact is not None:
            artifacts.append(fixture_artifact)

        state_text = {
            "TASK_STATE_COMPLETED": "Task completed",
            "TASK_STATE_INPUT_REQUIRED": "Additional input required",
            "TASK_STATE_WORKING": "Task is working",
            "TASK_STATE_REJECTED": "Task rejected",
        }.get(task_state, "Task status updated")
        task: dict[str, Any] = {
            "id": task_id,
            "contextId": context_id,
            "status": {
                "state": task_state,
                "timestamp": self._next_task_timestamp(),
                "message": self._agent_message(task_id, state_text),
            },
            "history": [deepcopy(message)],
            "metadata": metadata,
        }
        if artifacts:
            task["artifacts"] = artifacts
        return task

    def send_message(self, params: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(params, dict):
            raise AUECError(
                "E_A2A_INVALID_PARAMS", "SendMessage params must be an object"
            )
        message = self._validate_a2a_message(params.get("message"))
        message_id = self._message_id(message)
        manifest = self._extract_manifest_optional(message)
        configuration = self._configuration(params)
        history_length = self._history_length(configuration)

        if (
            "message-response" in message_id
            and message.get("taskId", message.get("task_id")) is None
        ):
            context_id = message.get(
                "contextId", message.get("context_id")
            ) or stable_id("ctx", {"message": message_id})
            return {
                "messageId": stable_id("msg", {"replyTo": message_id}),
                "contextId": context_id,
                "role": "ROLE_AGENT",
                "parts": [{"text": "Direct message response"}],
            }

        supplied_task_id = message.get("taskId", message.get("task_id"))
        supplied_context_id = message.get("contextId", message.get("context_id"))
        if supplied_task_id is not None and not isinstance(supplied_task_id, str):
            raise AUECError("E_A2A_INVALID_PARAMS", "taskId must be a string")
        if supplied_context_id is not None and not isinstance(supplied_context_id, str):
            raise AUECError("E_A2A_INVALID_PARAMS", "contextId must be a string")

        if isinstance(supplied_task_id, str):
            with self._lock:
                existing = deepcopy(self._tasks.get(supplied_task_id))
            if existing is None:
                raise AUECError("E_A2A_TASK_NOT_FOUND", "task not found")
            context_id = existing.get("contextId")
            if supplied_context_id is not None and supplied_context_id != context_id:
                raise AUECError(
                    "E_A2A_INVALID_PARAMS", "contextId does not match taskId"
                )
            history = existing.get("history", [])
            if isinstance(history, list) and any(
                isinstance(item, dict)
                and protocol_json_bytes(item) == protocol_json_bytes(message)
                for item in history
            ):
                return self._copy_task_for_response(existing, history_length)
            current = existing.get("status", {}).get("state")
            if current in {
                "TASK_STATE_COMPLETED",
                "TASK_STATE_FAILED",
                "TASK_STATE_CANCELED",
                "TASK_STATE_REJECTED",
            }:
                raise AUECError(
                    "E_A2A_UNSUPPORTED_OPERATION",
                    "terminal tasks cannot accept messages",
                )
            existing.setdefault("history", []).append(deepcopy(message))
            next_state = (
                "TASK_STATE_COMPLETED" if "complete-task" in message_id else current
            )
            if next_state not in {
                "TASK_STATE_INPUT_REQUIRED",
                "TASK_STATE_WORKING",
                "TASK_STATE_COMPLETED",
            }:
                next_state = "TASK_STATE_INPUT_REQUIRED"
            existing["status"] = {
                "state": next_state,
                "timestamp": self._next_task_timestamp(),
                "message": self._agent_message(
                    supplied_task_id,
                    "Task completed"
                    if next_state == "TASK_STATE_COMPLETED"
                    else "Additional input required",
                ),
            }
            with self._lock:
                self._tasks[supplied_task_id] = deepcopy(existing)
            return self._copy_task_for_response(existing, history_length)

        context_id = supplied_context_id or stable_id("ctx", {"message": message_id})
        request_metadata = (
            params.get("metadata") if isinstance(params.get("metadata"), dict) else {}
        )
        request_material = {
            "message": message,
            "configuration": configuration,
            "metadata": request_metadata,
        }
        request_digest = protocol_digest(request_material)

        # A2A 1.0 states that SendMessage MAY be idempotent; messageId is not a
        # mandatory global idempotency key. Generic A2A traffic therefore gets a
        # fresh task by default. AIEW manifest calls and callers that explicitly
        # provide metadata.idempotencyKey opt into strict replay semantics.
        explicit_key = request_metadata.get(
            "idempotencyKey", request_metadata.get("aiewIdempotencyKey")
        )
        if explicit_key is not None and (
            not isinstance(explicit_key, str) or not explicit_key
        ):
            raise AUECError(
                "E_A2A_INVALID_PARAMS", "idempotencyKey must be a non-empty string"
            )
        idempotency_key = (
            explicit_key
            if isinstance(explicit_key, str)
            else (f"aiew-manifest:{message_id}" if manifest is not None else None)
        )

        if idempotency_key is None:
            with self._lock:
                self._task_id_sequence += 1
                sequence = self._task_id_sequence
            task_id = stable_id(
                "task",
                {
                    "message": message_id,
                    "requestDigest": request_digest,
                    "sequence": sequence,
                },
            )
            task = self._build_generic_task(
                message,
                params,
                task_id=task_id,
                context_id=context_id,
                manifest=manifest,
            )
            task.setdefault("metadata", {}).update(
                {
                    "requestDigest": request_digest,
                    "idempotencyMode": "none",
                }
            )
            with self._lock:
                self._tasks[task_id] = deepcopy(task)
            return self._copy_task_for_response(task, history_length)

        # Explicit idempotency: the key, not messageId alone, selects a single
        # task. A changed semantic request under the same key fails closed.
        task_id = stable_id("task", {"idempotencyKey": idempotency_key})
        with self._lock:
            existing = deepcopy(self._tasks.get(task_id))
            if existing is not None:
                expected_context = existing.get("contextId")
                expected_digest = existing.get("metadata", {}).get("requestDigest")
                if expected_context != context_id or expected_digest != request_digest:
                    raise AUECError(
                        "E_A2A_IDEMPOTENCY",
                        "idempotency key collision with different input",
                    )
                return self._copy_task_for_response(existing, history_length)
            barrier = self._task_inflight.get(task_id)
            creator = barrier is None
            if creator:
                barrier = threading.Event()
                self._task_inflight[task_id] = barrier

        assert barrier is not None
        if not creator:
            if not barrier.wait(timeout=30.0):
                raise AUECError(
                    "E_A2A_INTERNAL", "timed out waiting for idempotent task creation"
                )
            with self._lock:
                existing = deepcopy(self._tasks.get(task_id))
            if existing is None:
                raise AUECError(
                    "E_A2A_INTERNAL",
                    "concurrent task creation did not publish a result",
                )
            expected_context = existing.get("contextId")
            expected_digest = existing.get("metadata", {}).get("requestDigest")
            if expected_context != context_id or expected_digest != request_digest:
                raise AUECError(
                    "E_A2A_IDEMPOTENCY",
                    "idempotency key collision with different input",
                )
            return self._copy_task_for_response(existing, history_length)

        try:
            task = self._build_generic_task(
                message,
                params,
                task_id=task_id,
                context_id=context_id,
                manifest=manifest,
            )
            task.setdefault("metadata", {}).update(
                {
                    "requestDigest": request_digest,
                    "idempotencyMode": "explicit",
                    "idempotencyKey": idempotency_key,
                }
            )
            with self._lock:
                existing = self._tasks.get(task_id)
                if existing is not None:
                    expected_context = existing.get("contextId")
                    expected_digest = existing.get("metadata", {}).get("requestDigest")
                    if (
                        expected_context != context_id
                        or expected_digest != request_digest
                    ):
                        raise AUECError(
                            "E_A2A_IDEMPOTENCY",
                            "idempotency key collision with different input",
                        )
                    task = deepcopy(existing)
                else:
                    self._tasks[task_id] = deepcopy(task)
            return self._copy_task_for_response(task, history_length)
        finally:
            with self._lock:
                published = self._task_inflight.pop(task_id, None)
                if published is not None:
                    published.set()

    def get_task(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = params.get("id") if isinstance(params, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise AUECError("E_A2A_INVALID_PARAMS", "task id required")
        history_length = self._history_length(params)
        with self._lock:
            task = deepcopy(self._tasks.get(task_id))
        if task is None:
            raise AUECError("E_A2A_TASK_NOT_FOUND", "task not found")
        return self._copy_task_for_response(task, history_length)

    def list_tasks(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        if not isinstance(params, dict):
            raise AUECError(
                "E_A2A_INVALID_PARAMS", "ListTasks params must be an object"
            )
        page_size = params.get("pageSize", params.get("page_size", 50))
        if (
            not isinstance(page_size, int)
            or isinstance(page_size, bool)
            or page_size < 1
            or page_size > 100
        ):
            raise AUECError("E_A2A_INVALID_PARAMS", "page size must be 1..100")
        page_token = params.get("pageToken", params.get("page_token", ""))
        if page_token in {None, ""}:
            offset = 0
        elif isinstance(page_token, str) and page_token.isdigit():
            offset = int(page_token)
        else:
            raise AUECError("E_A2A_INVALID_PARAMS", "invalid page token")
        context = params.get("contextId", params.get("context_id"))
        status_filter = params.get("status")
        include_artifacts = params.get(
            "includeArtifacts", params.get("include_artifacts", False)
        )
        if not isinstance(include_artifacts, bool):
            raise AUECError("E_A2A_INVALID_PARAMS", "includeArtifacts must be boolean")
        history_length = self._history_length(params)
        timestamp_after = params.get(
            "statusTimestampAfter", params.get("status_timestamp_after")
        )

        with self._lock:
            tasks = [deepcopy(value) for value in self._tasks.values()]
        if isinstance(context, str):
            tasks = [task for task in tasks if task.get("contextId") == context]
        if isinstance(status_filter, str):
            tasks = [
                task
                for task in tasks
                if task.get("status", {}).get("state") == status_filter
            ]
        if isinstance(timestamp_after, str):
            tasks = [
                task
                for task in tasks
                if str(task.get("status", {}).get("timestamp", "")) > timestamp_after
            ]
        tasks.sort(
            key=lambda task: str(task.get("status", {}).get("timestamp", "")),
            reverse=True,
        )

        page = tasks[offset : offset + page_size]
        output: list[dict[str, Any]] = []
        for task in page:
            projected = self._copy_task_for_response(task, history_length)
            if not include_artifacts:
                projected.pop("artifacts", None)
            output.append(projected)
        next_offset = offset + len(page)
        return {
            "tasks": output,
            "nextPageToken": str(next_offset) if next_offset < len(tasks) else "",
        }

    def cancel_task(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = params.get("id") if isinstance(params, dict) else None
        if not isinstance(task_id, str) or not task_id:
            raise AUECError("E_A2A_INVALID_PARAMS", "task id required")
        with self._lock:
            task = deepcopy(self._tasks.get(task_id))
        if task is None:
            raise AUECError("E_A2A_TASK_NOT_FOUND", "task not found")
        current = task.get("status", {}).get("state")
        if current in {
            "TASK_STATE_COMPLETED",
            "TASK_STATE_FAILED",
            "TASK_STATE_REJECTED",
            "TASK_STATE_CANCELED",
        }:
            raise AUECError("E_A2A_TASK_NOT_CANCELABLE", "task is not cancelable")
        task["status"] = {
            "state": "TASK_STATE_CANCELED",
            "timestamp": self._next_task_timestamp(),
            "message": self._agent_message(task_id, "Task canceled"),
        }
        with self._lock:
            self._tasks[task_id] = deepcopy(task)
        return deepcopy(task)

    def extended_agent_card(self, base_url: str) -> dict[str, Any]:
        # The extended card remains schema-compatible with AgentCard. AIEW-specific
        # semantics are expressed through the standard extensions collection rather
        # than a non-standard top-level metadata field.
        return self.agent_card(base_url)
