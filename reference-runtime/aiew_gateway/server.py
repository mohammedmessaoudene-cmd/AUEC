# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import math
import ipaddress
import secrets
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from aiew_uc.errors import AUECError

from .core import (
    A2A_EXTENSION_URI,
    A2A_PROTOCOL_VERSION,
    AIEW_GATEWAY_VERSION,
    GatewayState,
    MCP_LEGACY_VERSION,
    MCP_MODERN_VERSION,
    MCP_SUPPORTED_VERSIONS,
)
from .source_offer import require_exact_source_offer, source_offer_payload

MAX_BODY = 2_097_152
MAX_PROTOCOL_JSON_DEPTH = 64
MAX_PROTOCOL_JSON_NODES = 100_000


def _protocol_json_bytes(value: Any) -> bytes:
    """Encode ordinary MCP/A2A wire JSON deterministically.

    AUEC canonical JSON deliberately forbids floating point values. MCP and A2A
    wire envelopes do not. Keep those two contracts separate: manifests are
    validated by the AUEC runtime, while protocol envelopes accept finite JSON
    numbers and remain duplicate-key/NaN safe.
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
            "E_PROTOCOL_JSON_ENCODE", "wire value is not valid JSON"
        ) from exc


def _protocol_json_loads(raw: bytes) -> Any:
    if len(raw) > MAX_BODY:
        raise AUECError("E_PAYLOAD_SIZE", "request body exceeds bound")

    def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                raise AUECError("E_DUPLICATE_KEY", f"duplicate JSON key: {key}")
            obj[key] = value
        return obj

    def reject_constant(value: str) -> Any:
        raise AUECError("E_NONFINITE_NUMBER", f"non-finite JSON number: {value}")

    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=no_duplicates,
            parse_constant=reject_constant,
        )
    except AUECError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AUECError("E_JSON_PARSE", "malformed JSON request") from exc

    stack: list[tuple[Any, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_PROTOCOL_JSON_NODES:
            raise AUECError("E_JSON_NODES", "JSON value exceeds node bound")
        if depth > MAX_PROTOCOL_JSON_DEPTH:
            raise AUECError("E_JSON_DEPTH", "JSON value exceeds depth bound")
        if isinstance(current, float) and not math.isfinite(current):
            raise AUECError("E_NONFINITE_NUMBER", "non-finite JSON number")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)
    return value


def _validated_response_header(name: Any, value: Any) -> tuple[str, str]:
    """Reject response headers that could create a second HTTP response."""
    raw_name = str(name)
    raw_value = str(value)
    safe_name = raw_name.replace("\r", "").replace("\n", "").replace(":", "")
    safe_value = raw_value.replace("\r", "").replace("\n", "")
    if not safe_name or safe_name != raw_name or safe_value != raw_value:
        raise ValueError("unsafe HTTP response header")
    return safe_name, safe_value


class GatewayHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    allow_reuse_address = True
    # Base TCPServer defaults to a backlog of five. That creates avoidable
    # connection resets under ordinary agent fan-out, before the AUEC logic is
    # even reached. Keep the queue bounded but large enough for the published
    # concurrency profile.
    request_queue_size = 128

    def __init__(
        self, server_address: tuple[str, int], state: GatewayState | None = None
    ):
        self.state = state or GatewayState()
        super().__init__(server_address, GatewayRequestHandler)

    def handle_error(self, request: Any, client_address: tuple[str, int]) -> None:
        """Suppress expected peer disconnect noise, preserve all other errors.

        A client may deliberately reset a connection after sending an oversized
        request line or hostile payload.  The standard library can then raise
        while attempting to write its rejection response.  This is a transport
        teardown, not an application failure, and must not emit a misleading
        server traceback.  Unexpected exceptions still use the default handler.
        """
        exc = sys.exc_info()[1]
        if isinstance(
            exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)
        ):
            return
        super().handle_error(request, client_address)


class GatewayRequestHandler(BaseHTTPRequestHandler):
    server: GatewayHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Suppressed by default for deterministic test logs.
        return

    @property
    def base_url(self) -> str:
        host = (
            self.headers.get("Host")
            or f"{self.server.server_address[0]}:{self.server.server_address[1]}"
        )
        scheme = "https" if self.headers.get("X-Forwarded-Proto") == "https" else "http"
        return f"{scheme}://{host}"

    def _send_bytes(
        self,
        status: int,
        body: bytes = b"",
        *,
        content_type: str = "application/json",
        headers: dict[str, str] | None = None,
        cache_control: str | None = "no-store",
    ) -> None:
        self.send_response(status)
        if status != 304:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
        if cache_control is not None:
            self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        if headers:
            for key, value in headers.items():
                safe_key, safe_value = _validated_response_header(key, value)
                self.send_header(safe_key, safe_value)
        self.end_headers()
        if body and status != 304:
            self.wfile.write(body)

    def _send_json(
        self, status: int, value: Any, *, headers: dict[str, str] | None = None
    ) -> None:
        self._send_bytes(status, _protocol_json_bytes(value), headers=headers)

    def _send_a2a_json(
        self, status: int, value: Any, *, headers: dict[str, str] | None = None
    ) -> None:
        merged = {"A2A-Version": A2A_PROTOCOL_VERSION}
        if headers:
            merged.update(headers)
        self._send_bytes(
            status,
            _protocol_json_bytes(value),
            content_type="application/json",
            headers=merged,
        )

    @staticmethod
    def _a2a_error_detail(
        reason: str, metadata: dict[str, str] | None = None
    ) -> dict[str, Any]:
        detail: dict[str, Any] = {
            "@type": "type.googleapis.com/google.rpc.ErrorInfo",
            "reason": reason,
            "domain": "a2a-protocol.org",
        }
        if metadata:
            detail["metadata"] = metadata
        return detail

    def _a2a_rest_error(
        self,
        status: int,
        reason: str,
        message: str,
        *,
        metadata: dict[str, str] | None = None,
    ) -> None:
        status_name = {
            400: "FAILED_PRECONDITION",
            404: "NOT_FOUND",
            409: "FAILED_PRECONDITION",
            415: "INVALID_ARGUMENT",
            422: "INVALID_ARGUMENT",
            500: "INTERNAL",
            502: "INTERNAL",
        }.get(status, "UNKNOWN")
        self._send_a2a_json(
            status,
            {
                "error": {
                    "code": status,
                    "status": status_name,
                    "message": message[:256],
                    "details": [self._a2a_error_detail(reason, metadata)],
                }
            },
        )

    def _a2a_version_and_extensions(self) -> tuple[str, set[str]]:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        header_version = self.headers.get("A2A-Version")
        query_version = query.get("A2A-Version", [None])[0]
        if header_version and query_version and header_version != query_version:
            return "__MISMATCH__", set()
        # A2A 1.0 requires the service parameter; an empty value remains legacy 0.3.
        version = (header_version or query_version or "0.3").strip() or "0.3"
        raw_extensions = self.headers.get("A2A-Extensions", "")
        extensions = {
            item.strip() for item in raw_extensions.split(",") if item.strip()
        }
        return version, extensions

    def _validate_a2a_service_parameters(
        self,
        *,
        request_id: Any | None,
        jsonrpc: bool,
        require_extension: bool,
    ) -> bool:
        version, extensions = self._a2a_version_and_extensions()
        if version != A2A_PROTOCOL_VERSION:
            if jsonrpc:
                self._send_json(
                    400,
                    self._rpc_error(
                        request_id,
                        -32009,
                        "A2A protocol version not supported",
                        [
                            self._a2a_error_detail(
                                "VERSION_NOT_SUPPORTED",
                                {
                                    "requestedVersion": version,
                                    "supportedVersions": A2A_PROTOCOL_VERSION,
                                },
                            )
                        ],
                    ),
                    headers={"A2A-Version": A2A_PROTOCOL_VERSION},
                )
            else:
                self._a2a_rest_error(
                    400,
                    "VERSION_NOT_SUPPORTED",
                    "The requested A2A protocol version is not supported",
                    metadata={
                        "requestedVersion": version,
                        "supportedVersions": A2A_PROTOCOL_VERSION,
                    },
                )
            return False
        if require_extension and A2A_EXTENSION_URI not in extensions:
            if jsonrpc:
                self._send_json(
                    400,
                    self._rpc_error(
                        request_id,
                        -32008,
                        "Required A2A extension was not activated",
                        [
                            self._a2a_error_detail(
                                "EXTENSION_SUPPORT_REQUIRED",
                                {"requiredExtension": A2A_EXTENSION_URI},
                            )
                        ],
                    ),
                    headers={"A2A-Version": A2A_PROTOCOL_VERSION},
                )
            else:
                self._a2a_rest_error(
                    400,
                    "EXTENSION_SUPPORT_REQUIRED",
                    "The required AIEW extension was not activated",
                    metadata={"requiredExtension": A2A_EXTENSION_URI},
                )
            return False
        return True

    def _discard_optional_body(self) -> None:
        """Consume and ignore an optional bounded request body.

        A2A HTTP+JSON routes such as ``POST /tasks/{id}:cancel`` carry all
        normative parameters in the URL and therefore do not require a body.
        Some clients nevertheless send ``{}``.  On HTTP/1.1 that payload MUST
        be drained before the connection is reused; otherwise the unread bytes
        become a prefix of the next request method (for example ``{}POST``).
        """
        transfer_encoding = self.headers.get("Transfer-Encoding")
        if transfer_encoding and transfer_encoding.lower().strip() not in {
            "",
            "identity",
        }:
            self.close_connection = True
            raise AUECError(
                "E_HTTP_TRANSFER_ENCODING", "chunked request bodies are not supported"
            )
        length_raw = self.headers.get("Content-Length")
        if length_raw is None:
            return
        if not length_raw.isdigit():
            self.close_connection = True
            raise AUECError("E_HTTP_LENGTH", "invalid Content-Length")
        length = int(length_raw, 10)
        if length < 0 or length > MAX_BODY:
            self.close_connection = True
            raise AUECError("E_PAYLOAD_SIZE", "request body exceeds bound")
        if length == 0:
            return
        raw = self.rfile.read(length)
        if len(raw) != length:
            self.close_connection = True
            raise AUECError("E_HTTP_TRUNCATED", "truncated request body")

    def _read_json(self) -> Any:
        length_raw = self.headers.get("Content-Length")
        if length_raw is None or not length_raw.isdigit():
            raise AUECError("E_HTTP_LENGTH", "Content-Length required")
        length = int(length_raw, 10)
        if length < 0 or length > MAX_BODY:
            raise AUECError("E_PAYLOAD_SIZE", "request body exceeds bound")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise AUECError("E_HTTP_TRUNCATED", "truncated request body")
        return _protocol_json_loads(raw)

    @staticmethod
    def _rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _rpc_error(
        request_id: Any, code: int, message: str, data: Any | None = None
    ) -> dict[str, Any]:
        error: dict[str, Any] = {"code": code, "message": message[:256]}
        if data is not None:
            error["data"] = data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}

    def _origin_allowed(self) -> bool:
        """Reject cross-origin access to the localhost MCP endpoint (DNS-rebinding defense)."""
        host_header = self.headers.get("Host", "")
        try:
            host_name = urlparse(f"//{host_header}").hostname
        except ValueError:
            return False
        local_names = {"localhost", "127.0.0.1", "::1"}
        if not host_name or host_name.lower() not in local_names:
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        try:
            parsed = urlparse(origin)
        except ValueError:
            return False
        return (
            parsed.scheme in {"http", "https"}
            and parsed.netloc.lower() == host_header.lower()
        )

    @staticmethod
    def _decode_mcp_header_value(value: str) -> str:
        """Apply RFC 9110 OWS trimming and SEP-2243 value decoding.

        Only a value carrying both sentinel delimiters is Base64-decoded.
        A missing prefix or suffix is ordinary literal text, as required by
        the approved SEP-2243 conformance table.
        """
        value = value.strip(" \t")
        prefix, suffix = "=?base64?", "?="
        if value.startswith(prefix) and value.endswith(suffix):
            encoded = value[len(prefix) : -len(suffix)]
            try:
                raw = base64.b64decode(encoded, validate=True)
                return raw.decode("utf-8", errors="strict")
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise ValueError("invalid base64 sentinel") from exc
        if any(ord(ch) < 0x20 or ord(ch) > 0x7E for ch in value):
            raise ValueError("plain header is not visible ASCII")
        return value

    def _is_modern_mcp(self, method: str, params: dict[str, Any]) -> bool:
        meta = params.get("_meta") if isinstance(params, dict) else None
        has_modern_meta = isinstance(meta, dict) and (
            "io.modelcontextprotocol/protocolVersion" in meta
            or "io.modelcontextprotocol/clientCapabilities" in meta
            or "io.modelcontextprotocol/clientInfo" in meta
        )
        return (
            method == "server/discover"
            or has_modern_meta
            or self.headers.get("MCP-Protocol-Version") == MCP_MODERN_VERSION
        )

    def _validate_modern_mcp_headers_and_meta(
        self, request_id: Any, method: str, params: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, tuple[int, dict[str, Any]] | None]:
        """Return validated metadata or an HTTP/JSON-RPC rejection tuple."""
        meta = params.get("_meta")
        if not isinstance(meta, dict):
            return None, (
                400,
                self._rpc_error(
                    request_id,
                    -32602,
                    "Invalid params: required _meta object is missing",
                ),
            )
        version = meta.get("io.modelcontextprotocol/protocolVersion")
        capabilities = meta.get("io.modelcontextprotocol/clientCapabilities")
        if not isinstance(version, str) or not version:
            return None, (
                400,
                self._rpc_error(
                    request_id,
                    -32602,
                    "Invalid params: protocolVersion metadata is required",
                ),
            )
        if not isinstance(capabilities, dict):
            return None, (
                400,
                self._rpc_error(
                    request_id,
                    -32602,
                    "Invalid params: clientCapabilities metadata is required",
                ),
            )
        client_info = meta.get("io.modelcontextprotocol/clientInfo")
        if client_info is not None and (
            not isinstance(client_info, dict)
            or not isinstance(client_info.get("name"), str)
            or not isinstance(client_info.get("version"), str)
        ):
            return None, (
                400,
                self._rpc_error(
                    request_id,
                    -32602,
                    "Invalid params: clientInfo must contain name and version",
                ),
            )

        accept = self.headers.get("Accept", "")
        accepted = {
            part.split(";", 1)[0].strip().lower()
            for part in accept.split(",")
            if part.strip()
        }
        if not {"application/json", "text/event-stream"}.issubset(accepted):
            return None, (
                400,
                self._rpc_error(
                    request_id,
                    -32020,
                    "Header mismatch: Accept must list application/json and text/event-stream",
                ),
            )

        header_version = self.headers.get("MCP-Protocol-Version")
        header_method = self.headers.get("Mcp-Method")
        if header_version != version:
            return None, (
                400,
                self._rpc_error(
                    request_id,
                    -32020,
                    "Header mismatch: MCP-Protocol-Version does not match request metadata",
                ),
            )
        if header_method != method:
            return None, (
                400,
                self._rpc_error(
                    request_id,
                    -32020,
                    "Header mismatch: Mcp-Method does not match the JSON-RPC method",
                ),
            )

        required_name: str | None = None
        if method in {"tools/call", "prompts/get"}:
            required_name = params.get("name")
        elif method == "resources/read":
            required_name = params.get("uri")
        if method in {"tools/call", "prompts/get", "resources/read"}:
            if not isinstance(required_name, str):
                return None, (
                    400,
                    self._rpc_error(
                        request_id,
                        -32602,
                        "Invalid params: named method requires name or uri",
                    ),
                )
            raw_header_name = self.headers.get("Mcp-Name")
            if raw_header_name is None:
                return None, (
                    400,
                    self._rpc_error(
                        request_id,
                        -32020,
                        "Header mismatch: required Mcp-Name is missing",
                    ),
                )
            try:
                decoded_name = self._decode_mcp_header_value(raw_header_name)
            except ValueError as exc:
                return None, (
                    400,
                    self._rpc_error(request_id, -32020, f"Header mismatch: {exc}"),
                )
            if decoded_name != required_name:
                return None, (
                    400,
                    self._rpc_error(
                        request_id,
                        -32020,
                        "Header mismatch: Mcp-Name does not match the request body",
                    ),
                )

        if method == "tools/call" and isinstance(required_name, str):
            descriptor = next(
                (
                    item
                    for item in self.server.state.mcp_tools_list().get("tools", [])
                    if item.get("name") == required_name
                ),
                None,
            )
            schema = (
                descriptor.get("inputSchema", {})
                if isinstance(descriptor, dict)
                else {}
            )
            properties = (
                schema.get("properties", {}) if isinstance(schema, dict) else {}
            )
            arguments = params.get("arguments", {})
            if not isinstance(arguments, dict):
                return None, (
                    400,
                    self._rpc_error(
                        request_id,
                        -32602,
                        "Invalid params: arguments must be an object",
                    ),
                )
            if isinstance(properties, dict):
                for param_name, definition in properties.items():
                    if (
                        not isinstance(definition, dict)
                        or "x-mcp-header" not in definition
                    ):
                        continue
                    suffix = definition.get("x-mcp-header")
                    if not isinstance(suffix, str) or not suffix:
                        return None, (
                            400,
                            self._rpc_error(
                                request_id,
                                -32602,
                                "Invalid params: malformed x-mcp-header annotation",
                            ),
                        )
                    if param_name not in arguments:
                        continue
                    body_value = arguments.get(param_name)
                    if not isinstance(body_value, str):
                        return None, (
                            400,
                            self._rpc_error(
                                request_id,
                                -32602,
                                "Invalid params: header-bound value must be a string",
                            ),
                        )
                    raw_header = self.headers.get(f"Mcp-Param-{suffix}")
                    if raw_header is None:
                        return None, (
                            400,
                            self._rpc_error(
                                request_id,
                                -32020,
                                "Header mismatch: required custom parameter header is missing",
                            ),
                        )
                    try:
                        decoded_header = self._decode_mcp_header_value(raw_header)
                    except ValueError as exc:
                        return None, (
                            400,
                            self._rpc_error(
                                request_id, -32020, f"Header mismatch: {exc}"
                            ),
                        )
                    if decoded_header != body_value:
                        return None, (
                            400,
                            self._rpc_error(
                                request_id,
                                -32020,
                                "Header mismatch: custom parameter header does not match request body",
                            ),
                        )

        if version not in MCP_SUPPORTED_VERSIONS or version != MCP_MODERN_VERSION:
            return None, (
                400,
                self._rpc_error(
                    request_id,
                    -32022,
                    "Unsupported protocol version",
                    {"supported": list(MCP_SUPPORTED_VERSIONS), "requested": version},
                ),
            )
        return meta, None

    # ----------------------- common response helpers -----------------------
    @staticmethod
    def _a2a_error_mapping(code: str) -> tuple[int, int, str, str]:
        mapping = {
            "E_RPC_REQUEST": (
                -32600,
                400,
                "INVALID_REQUEST",
                "Invalid JSON-RPC request",
            ),
            "E_RPC_PARAMS": (
                -32602,
                400,
                "INVALID_ARGUMENT",
                "Invalid JSON-RPC parameters",
            ),
            "E_A2A_INVALID_PARAMS": (
                -32602,
                400,
                "INVALID_ARGUMENT",
                "Invalid A2A parameters",
            ),
            "E_A2A_IDEMPOTENCY": (
                -32602,
                400,
                "INVALID_ARGUMENT",
                "Idempotency key collision",
            ),
            "E_A2A_TASK_NOT_FOUND": (-32001, 404, "TASK_NOT_FOUND", "Task not found"),
            "E_A2A_TASK_NOT_CANCELABLE": (
                -32002,
                409,
                "TASK_NOT_CANCELABLE",
                "Task is not cancelable",
            ),
            "E_A2A_PUSH_NOT_SUPPORTED": (
                -32003,
                400,
                "PUSH_NOTIFICATION_NOT_SUPPORTED",
                "Push notifications are not supported",
            ),
            "E_A2A_UNSUPPORTED_OPERATION": (
                -32004,
                400,
                "UNSUPPORTED_OPERATION",
                "Operation is not supported",
            ),
            "E_A2A_CONTENT_TYPE": (
                -32005,
                415,
                "CONTENT_TYPE_NOT_SUPPORTED",
                "Content type is not supported",
            ),
            "E_A2A_INVALID_AGENT_RESPONSE": (
                -32006,
                502,
                "INVALID_AGENT_RESPONSE",
                "Invalid agent response",
            ),
            "E_A2A_EXTENDED_NOT_CONFIGURED": (
                -32007,
                400,
                "EXTENDED_AGENT_CARD_NOT_CONFIGURED",
                "Extended agent card is not configured",
            ),
            "E_A2A_EXTENSION_REQUIRED": (
                -32008,
                400,
                "EXTENSION_SUPPORT_REQUIRED",
                "Required extension support is missing",
            ),
            "E_A2A_VERSION": (
                -32009,
                400,
                "VERSION_NOT_SUPPORTED",
                "A2A protocol version is not supported",
            ),
        }
        return mapping.get(
            code, (-32602, 400, "INVALID_ARGUMENT", "Invalid A2A parameters")
        )

    def _send_a2a_rpc_exception(self, request_id: Any, exc: AUECError) -> None:
        rpc_code, _http_status, reason, message = self._a2a_error_mapping(exc.info.code)
        data = (
            [self._a2a_error_detail(reason, {"aiewCode": exc.info.code})]
            if rpc_code <= -32001 and rpc_code >= -32099
            else None
        )
        self._send_json(
            200,
            self._rpc_error(request_id, rpc_code, message, data),
            headers={"A2A-Version": A2A_PROTOCOL_VERSION},
        )

    def _send_a2a_rest_exception(self, exc: AUECError) -> None:
        _rpc_code, http_status, reason, message = self._a2a_error_mapping(exc.info.code)
        self._a2a_rest_error(
            http_status, reason, message, metadata={"aiewCode": exc.info.code}
        )

    @staticmethod
    def _a2a_response_envelope(value: dict[str, Any]) -> dict[str, Any]:
        if isinstance(value, dict) and "role" in value and "status" not in value:
            return {"message": value}
        return {"task": value}

    @staticmethod
    def _payload_contains_auec_manifest(payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        params = payload.get("params", payload)
        if not isinstance(params, dict):
            return False
        message = params.get("message")
        if not isinstance(message, dict):
            return False
        parts = message.get("parts")
        if not isinstance(parts, list):
            return False
        for part in parts:
            if not isinstance(part, dict):
                continue
            data = part.get("data")
            if isinstance(data, dict) and (
                isinstance(data.get("manifest"), dict)
                or data.get("auecVersion") == "0.1"
            ):
                return True
        return False

    def _require_aiew_extension_if_needed(
        self, payload: Any, *, request_id: Any | None, jsonrpc: bool
    ) -> bool:
        if not self._payload_contains_auec_manifest(payload):
            return True
        _version, extensions = self._a2a_version_and_extensions()
        if A2A_EXTENSION_URI in extensions:
            return True
        if jsonrpc:
            self._send_json(
                200,
                self._rpc_error(
                    request_id,
                    -32008,
                    "Required A2A extension was not activated",
                    [
                        self._a2a_error_detail(
                            "EXTENSION_SUPPORT_REQUIRED",
                            {"requiredExtension": A2A_EXTENSION_URI},
                        )
                    ],
                ),
                headers={"A2A-Version": A2A_PROTOCOL_VERSION},
            )
        else:
            self._a2a_rest_error(
                400,
                "EXTENSION_SUPPORT_REQUIRED",
                "The required AIEW extension was not activated",
                metadata={"requiredExtension": A2A_EXTENSION_URI},
            )
        return False

    # ----------------------- MCP SSE/bidirectional --------------------------
    def _begin_sse(self, *, headers: dict[str, str] | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Content-Type-Options", "nosniff")
        if headers:
            for key, value in headers.items():
                safe_key, safe_value = _validated_response_header(key, value)
                self.send_header(safe_key, safe_value)
        self.end_headers()
        self.close_connection = True

    def _write_sse_json(self, value: dict[str, Any]) -> None:
        # MCP permits ordinary JSON numbers (for example SEP-1034 default 95.5).
        # AUEC canonical JSON remains strict internally, but the generic MCP wire
        # encoding must not reject valid protocol values.
        raw = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.wfile.write(b"event: message\n")
        self.wfile.write(b"data: " + raw + b"\n\n")
        self.wfile.flush()

    def _mcp_elicitation_params(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if tool_name == "test_elicitation":
            return {
                "message": arguments.get("message", "Please provide your information"),
                "requestedSchema": {
                    "type": "object",
                    "properties": {
                        "username": {
                            "type": "string",
                            "description": "User's response",
                        },
                        "email": {
                            "type": "string",
                            "description": "User's email address",
                        },
                    },
                    "required": ["username", "email"],
                },
            }
        if tool_name == "test_elicitation_sep1034_defaults":
            return {
                "message": "Provide values for all primitive fields",
                "requestedSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "default": "John Doe"},
                        "age": {"type": "integer", "default": 30},
                        "score": {"type": "number", "default": 95.5},
                        "status": {
                            "type": "string",
                            "enum": ["active", "inactive", "pending"],
                            "default": "active",
                        },
                        "verified": {"type": "boolean", "default": True},
                    },
                    "required": ["name", "age", "score", "status", "verified"],
                },
            }
        if tool_name == "test_elicitation_sep1330_enums":
            return {
                "message": "Select enum values",
                "requestedSchema": {
                    "type": "object",
                    "properties": {
                        "untitledSingle": {
                            "type": "string",
                            "enum": ["option1", "option2", "option3"],
                        },
                        "titledSingle": {
                            "type": "string",
                            "oneOf": [
                                {"const": "value1", "title": "First Option"},
                                {"const": "value2", "title": "Second Option"},
                                {"const": "value3", "title": "Third Option"},
                            ],
                        },
                        "legacyEnum": {
                            "type": "string",
                            "enum": ["opt1", "opt2", "opt3"],
                            "enumNames": ["Option One", "Option Two", "Option Three"],
                        },
                        "untitledMulti": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["option1", "option2", "option3"],
                            },
                        },
                        "titledMulti": {
                            "type": "array",
                            "items": {
                                "anyOf": [
                                    {"const": "value1", "title": "First Choice"},
                                    {"const": "value2", "title": "Second Choice"},
                                    {"const": "value3", "title": "Third Choice"},
                                ]
                            },
                        },
                    },
                    "required": [
                        "untitledSingle",
                        "titledSingle",
                        "legacyEnum",
                        "untitledMulti",
                        "titledMulti",
                    ],
                },
            }
        raise AUECError("E_MCP_TOOL_NOT_FOUND", "unknown elicitation fixture")

    def _handle_modern_mcp_progress_tool(
        self, request_id: Any, params: dict[str, Any]
    ) -> bool:
        """Emit 2026-07-28 progress notifications and the final result on one POST-SSE stream.

        Modern MCP is stateless at the transport layer: no legacy session is
        created or required. The progress token is opaque and is echoed exactly.
        """
        name = params.get("name") if isinstance(params, dict) else None
        if name != "test_tool_with_progress":
            return False
        meta = params.get("_meta", {}) if isinstance(params, dict) else {}
        token = meta.get("progressToken") if isinstance(meta, dict) else None
        result = self.server.state.mcp_tool_call(params)
        self._begin_sse(headers={"MCP-Protocol-Version": MCP_MODERN_VERSION})
        try:
            if token is not None:
                for progress in (0, 50, 100):
                    self._write_sse_json(
                        {
                            "jsonrpc": "2.0",
                            "method": "notifications/progress",
                            "params": {
                                "progressToken": token,
                                "progress": progress,
                                "total": 100,
                            },
                        }
                    )
                    time.sleep(0.055)
            self._write_sse_json(
                self._rpc_result(
                    request_id,
                    self.server.state.modern_result("tools/call", result),
                )
            )
        except (BrokenPipeError, ConnectionResetError):
            return True
        return True

    def _handle_modern_mcp_subscription(self, params: dict[str, Any]) -> None:
        notifications = (
            params.get("notifications", {}) if isinstance(params, dict) else {}
        )
        subscription_id, channel = self.server.state.open_mcp_subscription(
            notifications
        )
        self._begin_sse(headers={"MCP-Protocol-Version": MCP_MODERN_VERSION})
        try:
            self._write_sse_json(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/subscriptions/acknowledged",
                    "params": {
                        "_meta": {
                            "io.modelcontextprotocol/subscriptionId": subscription_id,
                        }
                    },
                }
            )
            deadline = time.monotonic() + 2.25
            while time.monotonic() < deadline:
                remaining = max(0.0, deadline - time.monotonic())
                try:
                    event = channel.get(timeout=min(0.25, remaining))
                except Exception:
                    continue
                self._write_sse_json(event)
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.server.state.close_mcp_subscription(subscription_id)

    def _handle_legacy_mcp_streaming_tool(
        self, request_id: Any, params: dict[str, Any]
    ) -> bool:
        name = params.get("name") if isinstance(params, dict) else None
        if name not in {
            "test_tool_with_logging",
            "test_tool_with_progress",
            "test_sampling",
            "test_elicitation",
            "test_elicitation_sep1034_defaults",
            "test_elicitation_sep1330_enums",
        }:
            return False
        session_id = self.headers.get("Mcp-Session-Id")
        state = self.server.state
        if not state.has_mcp_session(session_id):
            self._send_json(
                200, self._rpc_error(request_id, -32000, "MCP session required")
            )
            return True

        self._begin_sse(
            headers={
                "Mcp-Session-Id": str(session_id),
                "MCP-Protocol-Version": MCP_LEGACY_VERSION,
            }
        )
        try:
            if name == "test_tool_with_logging":
                for message in (
                    "Tool execution started",
                    "Tool processing data",
                    "Tool execution completed",
                ):
                    self._write_sse_json(
                        {
                            "jsonrpc": "2.0",
                            "method": "notifications/message",
                            "params": {
                                "level": "info",
                                "logger": "auec-gateway",
                                "data": message,
                            },
                        }
                    )
                    time.sleep(0.055)
                result = {
                    "content": [{"type": "text", "text": "Tool execution completed"}]
                }
            elif name == "test_tool_with_progress":
                meta = params.get("_meta", {}) if isinstance(params, dict) else {}
                token = meta.get("progressToken") if isinstance(meta, dict) else None
                if token is not None:
                    for progress in (0, 50, 100):
                        self._write_sse_json(
                            {
                                "jsonrpc": "2.0",
                                "method": "notifications/progress",
                                "params": {
                                    "progressToken": token,
                                    "progress": progress,
                                    "total": 100,
                                },
                            }
                        )
                        time.sleep(0.055)
                result = {"content": [{"type": "text", "text": "Progress completed"}]}
            else:
                arguments = (
                    params.get("arguments", {}) if isinstance(params, dict) else {}
                )
                if not isinstance(arguments, dict):
                    arguments = {}
                if name == "test_sampling":
                    client_method = "sampling/createMessage"
                    client_params = {
                        "messages": [
                            {
                                "role": "user",
                                "content": {
                                    "type": "text",
                                    "text": arguments.get(
                                        "prompt", "Test prompt for sampling"
                                    ),
                                },
                            }
                        ],
                        "maxTokens": 100,
                    }
                else:
                    client_method = "elicitation/create"
                    client_params = self._mcp_elicitation_params(name, arguments)
                client_request, event = state.create_mcp_client_request(
                    str(session_id), client_method, client_params
                )
                self._write_sse_json(client_request)
                response = state.wait_mcp_client_response(
                    str(session_id), str(client_request["id"]), event, timeout=8.0
                )
                client_result = response.get("result", {})
                if name == "test_sampling":
                    content = (
                        client_result.get("content", {})
                        if isinstance(client_result, dict)
                        else {}
                    )
                    sample_text = (
                        content.get("text", "client sampling completed")
                        if isinstance(content, dict)
                        else "client sampling completed"
                    )
                    result = {
                        "content": [
                            {"type": "text", "text": f"LLM response: {sample_text}"}
                        ]
                    }
                else:
                    action = (
                        client_result.get("action", "accept")
                        if isinstance(client_result, dict)
                        else "accept"
                    )
                    result = {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Elicitation completed: action={action}",
                            }
                        ]
                    }
            self._write_sse_json(self._rpc_result(request_id, result))
        except AUECError as exc:
            self._write_sse_json(
                self._rpc_error(
                    request_id,
                    -32000,
                    "AIEW gateway rejected request",
                    {"aiewCode": exc.info.code},
                )
            )
        except (BrokenPipeError, ConnectionResetError):
            return True
        except Exception:
            try:
                self._write_sse_json(
                    self._rpc_error(request_id, -32603, "Internal error")
                )
            except (BrokenPipeError, ConnectionResetError):
                pass
        return True

    # ----------------------------- HTTP routes -------------------------------
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/healthz":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "name": "auec-gateway",
                    "version": AIEW_GATEWAY_VERSION,
                },
            )
            return
        if path == "/source":
            self._send_json(200, source_offer_payload())
            return
        if path == "/browser-harness":
            html = b"""<!doctype html><meta charset=utf-8><title>AUEC browser harness</title><main id=app>AUEC browser harness</main>"""
            self._send_bytes(
                200,
                html,
                content_type="text/html; charset=utf-8",
                headers={
                    "Permissions-Policy": "tools=(self)",
                    "Content-Security-Policy": "default-src 'self'; connect-src 'self'; script-src 'self' 'unsafe-inline'",
                },
            )
            return
        if path == "/.well-known/agent-card.json":
            card = self.server.state.agent_card(self.base_url)
            body = _protocol_json_bytes(card)
            etag = '"' + hashlib.sha256(body).hexdigest() + '"'
            last_modified = "Wed, 29 Jul 2026 00:00:00 GMT"
            if self.headers.get("If-None-Match") == etag:
                self._send_bytes(
                    304,
                    b"",
                    headers={"ETag": etag, "Last-Modified": last_modified},
                    cache_control="public, max-age=300",
                )
                return
            self._send_bytes(
                200,
                body,
                headers={
                    "ETag": etag,
                    "Last-Modified": last_modified,
                    "A2A-Version": A2A_PROTOCOL_VERSION,
                },
                cache_control="public, max-age=300",
            )
            return
        if path == "/extendedAgentCard":
            if not self._validate_a2a_service_parameters(
                request_id=None, jsonrpc=False, require_extension=False
            ):
                return
            self._send_a2a_json(
                200, self.server.state.extended_agent_card(self.base_url)
            )
            return
        if "/pushNotificationConfigs" in path:
            if not self._validate_a2a_service_parameters(
                request_id=None, jsonrpc=False, require_extension=False
            ):
                return
            self._a2a_rest_error(
                400,
                "PUSH_NOTIFICATION_NOT_SUPPORTED",
                "Push notifications are not supported",
            )
            return
        if path.startswith("/tasks/") and path.endswith(":subscribe"):
            if not self._validate_a2a_service_parameters(
                request_id=None, jsonrpc=False, require_extension=False
            ):
                return
            self._a2a_rest_error(
                400, "UNSUPPORTED_OPERATION", "Streaming is not supported"
            )
            return
        if path.startswith("/tasks/"):
            if not self._validate_a2a_service_parameters(
                request_id=None, jsonrpc=False, require_extension=False
            ):
                return
            task_id = path[len("/tasks/") :]
            query = parse_qs(parsed.query)
            params: dict[str, Any] = {"id": task_id}
            if "historyLength" in query:
                try:
                    params["historyLength"] = int(query["historyLength"][0])
                except ValueError:
                    self._a2a_rest_error(
                        400, "INVALID_ARGUMENT", "Invalid historyLength"
                    )
                    return
            try:
                self._send_a2a_json(200, self.server.state.get_task(params))
            except AUECError as exc:
                self._send_a2a_rest_exception(exc)
            return
        if path == "/tasks":
            if not self._validate_a2a_service_parameters(
                request_id=None, jsonrpc=False, require_extension=False
            ):
                return
            query = parse_qs(parsed.query)
            params: dict[str, Any] = {}
            converters = {
                "pageSize": int,
                "historyLength": int,
            }
            for key, converter in converters.items():
                if key in query:
                    try:
                        params[key] = converter(query[key][0])
                    except ValueError:
                        self._a2a_rest_error(400, "INVALID_ARGUMENT", f"Invalid {key}")
                        return
            for key in ("contextId", "status", "pageToken", "statusTimestampAfter"):
                if key in query:
                    params[key] = query[key][0]
            if "includeArtifacts" in query:
                raw = query["includeArtifacts"][0].lower()
                if raw not in {"true", "false"}:
                    self._a2a_rest_error(
                        400, "INVALID_ARGUMENT", "Invalid includeArtifacts"
                    )
                    return
                params["includeArtifacts"] = raw == "true"
            try:
                self._send_a2a_json(200, self.server.state.list_tasks(params))
            except AUECError as exc:
                self._send_a2a_rest_exception(exc)
            return
        if path == "/mcp":
            self._send_json(
                405,
                {"error": "MCP standalone SSE GET transport is not enabled"},
                headers={"Allow": "POST, DELETE"},
            )
            return
        self._send_json(404, {"error": {"code": 404, "message": "not_found"}})

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path == "/mcp":
            if self.headers.get("MCP-Protocol-Version") == MCP_MODERN_VERSION:
                self._send_json(
                    405, {"error": "method_not_allowed"}, headers={"Allow": "POST"}
                )
            else:
                session_id = self.headers.get("Mcp-Session-Id")
                if (
                    session_id is not None
                    and not self.server.state.unregister_mcp_session(session_id)
                ):
                    self._send_json(
                        404, self._rpc_error(None, -32001, "Unknown MCP session")
                    )
                else:
                    self._send_json(200, {})
            return
        if "/pushNotificationConfigs/" in path:
            if not self._validate_a2a_service_parameters(
                request_id=None, jsonrpc=False, require_extension=False
            ):
                return
            self._a2a_rest_error(
                400,
                "PUSH_NOTIFICATION_NOT_SUPPORTED",
                "Push notifications are not supported",
            )
            return
        self._send_json(404, {"error": {"code": 404, "message": "not_found"}})

    def do_POST(self) -> None:
        path = urlparse(self.path).path

        # A2A CancelTask and SubscribeToTask carry their task identifier in the
        # route and have no request body in the HTTP+JSON binding. Dispatch them
        # before Content-Type and JSON-body validation; requiring an artificial
        # body turns a legitimate missing task into an unrelated HTTP 400.
        if path.startswith("/tasks/") and path.endswith(":cancel"):
            try:
                self._discard_optional_body()
            except AUECError as exc:
                self._a2a_rest_error(400, "INVALID_ARGUMENT", exc.info.message)
                return
            if not self._validate_a2a_service_parameters(
                request_id=None, jsonrpc=False, require_extension=False
            ):
                return
            task_id = path[len("/tasks/") : -len(":cancel")]
            try:
                self._send_a2a_json(200, self.server.state.cancel_task({"id": task_id}))
            except AUECError as exc:
                self._send_a2a_rest_exception(exc)
            return
        if path.startswith("/tasks/") and path.endswith(":subscribe"):
            try:
                self._discard_optional_body()
            except AUECError as exc:
                self._a2a_rest_error(400, "INVALID_ARGUMENT", exc.info.message)
                return
            if not self._validate_a2a_service_parameters(
                request_id=None, jsonrpc=False, require_extension=False
            ):
                return
            self._a2a_rest_error(
                400, "UNSUPPORTED_OPERATION", "Streaming is not supported"
            )
            return

        a2a_rest_paths = (
            path in {"/message:send", "/message:stream"}
            or (
                path.startswith("/tasks/")
                and (path.endswith(":cancel") or path.endswith(":subscribe"))
            )
            or "/pushNotificationConfigs" in path
        )
        if a2a_rest_paths:
            content_type = (
                self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            )
            if content_type not in {"application/json", "application/a2a+json"}:
                # Reject before decoding and close HTTP/1.1 so an unread body cannot
                # desynchronize a later request on the same socket.
                self.close_connection = True
                self._a2a_rest_error(
                    415, "CONTENT_TYPE_NOT_SUPPORTED", "Content type is not supported"
                )
                return
        if path in {"/", "/a2a"}:
            content_type = (
                self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            )
            if content_type not in {"application/json", "application/a2a+json"}:
                # JSON-RPC binding: return the protocol's ContentTypeNotSupported
                # mapping (-32005) and close before reading the hostile body.
                self.close_connection = True
                self._send_json(
                    415,
                    self._rpc_error(
                        None,
                        -32005,
                        "Content type is not supported",
                        [self._a2a_error_detail("CONTENT_TYPE_NOT_SUPPORTED")],
                    ),
                    headers={
                        "A2A-Version": A2A_PROTOCOL_VERSION,
                        "Connection": "close",
                    },
                )
                return
        if path == "/mcp" and not self._origin_allowed():
            self.close_connection = True
            self._send_json(
                403,
                self._rpc_error(None, -32023, "Forbidden Origin"),
                headers={"Connection": "close"},
            )
            return
        try:
            payload = self._read_json()
        except AUECError as exc:
            if path == "/mcp":
                self._send_json(
                    400,
                    self._rpc_error(
                        None, -32700, "Parse error", {"aiewCode": exc.info.code}
                    ),
                )
            elif path in {"/", "/a2a"}:
                self._send_json(
                    400,
                    self._rpc_error(None, -32700, "Parse error"),
                    headers={"A2A-Version": A2A_PROTOCOL_VERSION},
                )
            else:
                self._a2a_rest_error(400, "INVALID_ARGUMENT", "Malformed JSON request")
            return

        if path == "/mcp":
            self._handle_mcp(payload)
            return
        if path in {"/", "/a2a"}:
            self._handle_a2a(payload)
            return
        if path == "/message:send":
            if not self._validate_a2a_service_parameters(
                request_id=None, jsonrpc=False, require_extension=False
            ):
                return
            if not self._require_aiew_extension_if_needed(
                payload, request_id=None, jsonrpc=False
            ):
                return
            try:
                value = self.server.state.send_message(payload)
                self._send_a2a_json(200, self._a2a_response_envelope(value))
            except AUECError as exc:
                self._send_a2a_rest_exception(exc)
            return
        if path == "/message:stream":
            if not self._validate_a2a_service_parameters(
                request_id=None, jsonrpc=False, require_extension=False
            ):
                return
            self._a2a_rest_error(
                400, "UNSUPPORTED_OPERATION", "Streaming is not supported"
            )
            return
        if "/pushNotificationConfigs" in path:
            if not self._validate_a2a_service_parameters(
                request_id=None, jsonrpc=False, require_extension=False
            ):
                return
            self._a2a_rest_error(
                400,
                "PUSH_NOTIFICATION_NOT_SUPPORTED",
                "Push notifications are not supported",
            )
            return
        if path == "/execute":
            manifest = payload.get("manifest") if isinstance(payload, dict) else None
            if not isinstance(manifest, dict):
                self._send_json(400, {"error": {"code": "E_HTTP_MANIFEST"}})
                return
            result = self.server.state.execute_manifest(manifest)
            self._send_json(200 if result.get("status") == "succeeded" else 422, result)
            return
        self._send_json(404, {"error": {"code": 404, "message": "not_found"}})

    def _validate_rpc_request(
        self, payload: Any
    ) -> tuple[Any, str, dict[str, Any], bool]:
        if (
            not isinstance(payload, dict)
            or payload.get("jsonrpc") != "2.0"
            or not isinstance(payload.get("method"), str)
        ):
            raise AUECError("E_RPC_REQUEST", "invalid JSON-RPC request")
        request_id = payload.get("id")
        params = payload.get("params", {})
        if not isinstance(params, dict):
            raise AUECError("E_RPC_PARAMS", "params must be object")
        return request_id, payload["method"], params, "id" not in payload

    def _handle_mcp(self, payload: Any) -> None:
        state = self.server.state
        # A server-to-client request response is POSTed back to the same MCP
        # endpoint. Resolve it before applying request-only validation.
        if (
            isinstance(payload, dict)
            and payload.get("jsonrpc") == "2.0"
            and "id" in payload
            and "method" not in payload
            and ("result" in payload or "error" in payload)
        ):
            session_id = self.headers.get("Mcp-Session-Id")
            if state.resolve_mcp_client_response(session_id, payload):
                self._send_bytes(202, b"", content_type="application/json")
            else:
                self._send_json(
                    400,
                    self._rpc_error(
                        payload.get("id"), -32600, "Unknown client response"
                    ),
                )
            return

        try:
            request_id, method, params, is_notification = self._validate_rpc_request(
                payload
            )
            modern = self._is_modern_mcp(method, params)

            if modern:
                _meta, rejection = self._validate_modern_mcp_headers_and_meta(
                    request_id, method, params
                )
                if rejection is not None:
                    status, body = rejection
                    self._send_json(status, body)
                    return
                if method == "server/discover":
                    result = state.mcp_discover()
                elif method == "tools/list":
                    result = state.modern_result(method, state.mcp_tools_list())
                elif method == "subscriptions/listen":
                    self._handle_modern_mcp_subscription(params)
                    return
                elif method == "tools/call":
                    if self._handle_modern_mcp_progress_tool(request_id, params):
                        return
                    result = state.modern_result(method, state.mcp_tool_call(params))
                elif method == "resources/list":
                    result = state.modern_result(method, state.mcp_resources_list())
                elif method == "resources/templates/list":
                    result = state.modern_result(
                        method, state.mcp_resource_templates_list()
                    )
                elif method == "resources/read":
                    result = state.modern_result(
                        method, state.mcp_resource_read(params)
                    )
                elif method == "prompts/list":
                    result = state.modern_result(method, state.mcp_prompts_list())
                elif method == "prompts/get":
                    result = state.modern_result(method, state.mcp_prompt_get(params))
                elif method == "completion/complete":
                    result = state.modern_result(
                        method, state.mcp_completion_complete(params)
                    )
                else:
                    self._send_json(
                        404, self._rpc_error(request_id, -32601, "Method not found")
                    )
                    return
                if is_notification:
                    self._send_bytes(202, b"", content_type="application/json")
                else:
                    self._send_json(
                        200,
                        self._rpc_result(request_id, result),
                        headers={"MCP-Protocol-Version": MCP_MODERN_VERSION},
                    )
                return

            if method == "initialize":
                result = state.mcp_initialize(params)
                session_id = "aiew-" + secrets.token_hex(12)
                state.register_mcp_session(session_id)
                headers = {
                    "Mcp-Session-Id": session_id,
                    "MCP-Protocol-Version": MCP_LEGACY_VERSION,
                }
            elif method in {"notifications/initialized", "notifications/cancelled"}:
                self._send_bytes(202, b"", content_type="application/json")
                return
            elif method == "ping":
                result, headers = {}, {}
            elif method == "tools/list":
                result, headers = state.mcp_tools_list(), {}
            elif method == "tools/call":
                if self._handle_legacy_mcp_streaming_tool(request_id, params):
                    return
                result, headers = state.mcp_tool_call(params), {}
            elif method == "resources/list":
                result, headers = state.mcp_resources_list(), {}
            elif method == "resources/templates/list":
                result, headers = state.mcp_resource_templates_list(), {}
            elif method == "resources/read":
                result, headers = state.mcp_resource_read(params), {}
            elif method == "resources/subscribe":
                result, headers = state.mcp_subscribe(params), {}
            elif method == "resources/unsubscribe":
                result, headers = state.mcp_unsubscribe(params), {}
            elif method == "prompts/list":
                result, headers = state.mcp_prompts_list(), {}
            elif method == "prompts/get":
                result, headers = state.mcp_prompt_get(params), {}
            elif method == "logging/setLevel":
                result, headers = state.set_log_level(params), {}
            elif method == "completion/complete":
                result, headers = (
                    {"completion": {"values": [], "total": 0, "hasMore": False}},
                    {},
                )
            else:
                self._send_json(
                    200, self._rpc_error(request_id, -32601, "Method not found")
                )
                return
            if is_notification:
                self._send_bytes(
                    202, b"", content_type="application/json", headers=headers
                )
            else:
                self._send_json(
                    200, self._rpc_result(request_id, result), headers=headers
                )
        except AUECError as exc:
            request_id = payload.get("id") if isinstance(payload, dict) else None
            params = payload.get("params", {}) if isinstance(payload, dict) else {}
            method = payload.get("method", "") if isinstance(payload, dict) else ""
            modern = isinstance(params, dict) and self._is_modern_mcp(method, params)
            if modern and exc.info.code == "E_MCP_MISSING_CAPABILITY":
                capability = exc.info.message
                self._send_json(
                    400,
                    self._rpc_error(
                        request_id,
                        -32021,
                        "Missing required client capability",
                        {"requiredCapabilities": {capability: {}}},
                    ),
                )
                return
            if modern:
                code = (
                    -32602
                    if exc.info.code
                    in {
                        "E_RPC_PARAMS",
                        "E_MCP",
                        "E_MCP_STATE",
                        "E_MCP_TOOL_NOT_FOUND",
                        "E_MCP_RESOURCE_NOT_FOUND",
                        "E_MCP_PROMPT_NOT_FOUND",
                    }
                    else -32000
                )
                data: dict[str, Any] = {"aiewCode": exc.info.code}
                if (
                    exc.info.code == "E_MCP_RESOURCE_NOT_FOUND"
                    and isinstance(params, dict)
                    and isinstance(params.get("uri"), str)
                ):
                    data["uri"] = params["uri"]
                self._send_json(
                    400,
                    self._rpc_error(
                        request_id, code, "AIEW gateway rejected request", data
                    ),
                )
            else:
                rpc_code = (
                    -32602
                    if exc.info.code in {"E_RPC_REQUEST", "E_RPC_PARAMS", "E_MCP"}
                    else -32000
                )
                self._send_json(
                    200,
                    self._rpc_error(
                        request_id,
                        rpc_code,
                        "AIEW gateway rejected request",
                        {"aiewCode": exc.info.code},
                    ),
                )
        except Exception:
            request_id = payload.get("id") if isinstance(payload, dict) else None
            self._send_json(500, self._rpc_error(request_id, -32603, "Internal error"))

    def _handle_a2a(self, payload: Any) -> None:
        request_id = payload.get("id") if isinstance(payload, dict) else None
        if not self._validate_a2a_service_parameters(
            request_id=request_id, jsonrpc=True, require_extension=False
        ):
            return
        if not self._require_aiew_extension_if_needed(
            payload, request_id=request_id, jsonrpc=True
        ):
            return
        try:
            request_id, method, params, is_notification = self._validate_rpc_request(
                payload
            )
            if is_notification:
                self._send_bytes(
                    202,
                    b"",
                    content_type="application/json",
                    headers={"A2A-Version": A2A_PROTOCOL_VERSION},
                )
                return
            state = self.server.state
            if method == "SendMessage":
                result = self._a2a_response_envelope(state.send_message(params))
            elif method == "GetTask":
                result = state.get_task(params)
            elif method == "ListTasks":
                result = state.list_tasks(params)
            elif method == "CancelTask":
                result = state.cancel_task(params)
            elif method == "GetExtendedAgentCard":
                result = state.extended_agent_card(self.base_url)
            elif method in {"SendStreamingMessage", "SubscribeToTask"}:
                raise AUECError(
                    "E_A2A_UNSUPPORTED_OPERATION", "streaming not supported"
                )
            elif method in {
                "CreateTaskPushNotificationConfig",
                "GetTaskPushNotificationConfig",
                "ListTaskPushNotificationConfigs",
                "DeleteTaskPushNotificationConfig",
            }:
                raise AUECError(
                    "E_A2A_PUSH_NOT_SUPPORTED", "push notifications not supported"
                )
            else:
                self._send_json(
                    200,
                    self._rpc_error(request_id, -32601, "Method not found"),
                    headers={"A2A-Version": A2A_PROTOCOL_VERSION},
                )
                return
            self._send_json(
                200,
                self._rpc_result(request_id, result),
                headers={"A2A-Version": A2A_PROTOCOL_VERSION},
            )
        except AUECError as exc:
            self._send_a2a_rpc_exception(request_id, exc)
        except Exception:
            self._send_json(
                200,
                self._rpc_error(
                    request_id,
                    -32603,
                    "Internal error",
                    [self._a2a_error_detail("INVALID_AGENT_RESPONSE")],
                ),
                headers={"A2A-Version": A2A_PROTOCOL_VERSION},
            )


def _host_is_loopback(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def create_server(
    host: str = "127.0.0.1",
    port: int = 0,
    state: GatewayState | None = None,
    *,
    require_exact_source: bool | None = None,
) -> GatewayHTTPServer:
    enforce = (
        (not _host_is_loopback(host))
        if require_exact_source is None
        else require_exact_source
    )
    if enforce:
        require_exact_source_offer()
    return GatewayHTTPServer((host, port), state=state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AUEC reference gateway")
    parser.add_argument(
        "--require-exact-source-offer",
        action="store_true",
        help="fail startup unless the AGPL source URL, ref, and SHA-256 are exact",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--ready-file")
    parser.add_argument(
        "--source-offer",
        action="store_true",
        help="print corresponding-source metadata and exit",
    )
    args = parser.parse_args(argv)

    if args.source_offer:
        print(
            json.dumps(
                source_offer_payload(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0

    server = create_server(
        args.host,
        args.port,
        require_exact_source=(
            args.require_exact_source_offer or not _host_is_loopback(args.host)
        ),
    )
    address, port = server.server_address
    if args.ready_file:
        with open(args.ready_file, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                {"host": address, "port": port},
                handle,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.write("\n")

    stop = threading.Event()

    def _shutdown(_signum: int, _frame: Any) -> None:
        if not stop.is_set():
            stop.set()
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
