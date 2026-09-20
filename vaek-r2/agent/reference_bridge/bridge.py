"""Strict AI-output to typed Effect IR compiler. Never executes model output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

BYTES32 = re.compile(r"^0x[0-9a-fA-F]{64}$")
UINT = re.compile(r"^(0|[1-9][0-9]*)$")
MAX_U128 = 2**128 - 1
MAX_U64 = 2**64 - 1

COMMON = {
    "schemaVersion", "effectType", "executionId", "mandateId", "nonce", "validAfter", "deadline",
    "observationHash", "modelCommitment", "policyCommitment", "contextHash", "payload",
}
PAYLOAD_FIELDS = {
    "TRANSFER_ERC20": {"assetId", "recipientId", "requestedAmount"},
    "SWAP_EXACT_INPUT": {
        "assetInId", "assetOutId", "venueId", "recipientId", "maxInput", "minOutput",
        "quoteCommitment", "quoteValidUntil",
    },
    "BUY_SERVICE_ESCROW": {
        "providerId", "serviceId", "paymentAssetId", "maxPrice", "deliveryCommitment",
        "serviceDeadline", "evaluatorId",
    },
}
ID_FIELDS = {
    "assetId", "recipientId", "assetInId", "assetOutId", "venueId", "providerId",
    "serviceId", "paymentAssetId", "evaluatorId",
}
HASH_FIELDS = {
    "executionId", "mandateId", "observationHash", "modelCommitment", "policyCommitment",
    "contextHash", "quoteCommitment", "deliveryCommitment",
}
U64_FIELDS = {"nonce", "validAfter", "deadline", "quoteValidUntil", "serviceDeadline"}
U128_FIELDS = {"requestedAmount", "maxInput", "minOutput", "maxPrice"}
FORBIDDEN_NAMES = {"calldata", "selector", "adapter", "adapterAddress", "target", "bytes", "abi"}


class BridgeRejected(ValueError):
    pass


def _pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BridgeRejected(f"duplicate key: {key}")
        result[key] = value
    return result


def _number_rejected(value: str) -> None:
    raise BridgeRejected(f"JSON number forbidden; encode exact integers as decimal strings: {value}")


def strict_loads(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_int=_number_rejected, parse_float=_number_rejected)
    except (json.JSONDecodeError, TypeError) as exc:
        raise BridgeRejected("invalid JSON") from exc
    if not isinstance(value, dict):
        raise BridgeRejected("top-level object required")
    return value


def _uint(value: Any, maximum: int, field: str) -> int:
    if not isinstance(value, str) or not UINT.fullmatch(value):
        raise BridgeRejected(f"{field}: canonical unsigned decimal string required")
    parsed = int(value)
    if parsed > maximum:
        raise BridgeRejected(f"{field}: overflow")
    return parsed


def _bytes32(value: Any, field: str) -> str:
    if not isinstance(value, str) or not BYTES32.fullmatch(value):
        raise BridgeRejected(f"{field}: bytes32 hex required")
    return value.lower()


def compile_request(raw: str, catalogs: Mapping[str, set[str]]) -> tuple[dict[str, Any], bytes]:
    """Validate, resolve against caller-supplied symbolic catalogs, and canonicalize."""
    obj = strict_loads(raw)
    if set(obj) != COMMON:
        raise BridgeRejected(f"unknown or missing top-level fields: {sorted(set(obj) ^ COMMON)}")
    if obj["schemaVersion"] != "0.2" or obj["effectType"] not in PAYLOAD_FIELDS:
        raise BridgeRejected("unknown schema/effect")
    payload = obj["payload"]
    if not isinstance(payload, dict) or set(payload) != PAYLOAD_FIELDS[obj["effectType"]]:
        raise BridgeRejected("unknown or missing payload fields")
    if FORBIDDEN_NAMES.intersection(obj) or FORBIDDEN_NAMES.intersection(payload):
        raise BridgeRejected("executable or dispatch field forbidden")

    for field in HASH_FIELDS.intersection(obj):
        obj[field] = _bytes32(obj[field], field)
    for field in HASH_FIELDS.intersection(payload):
        payload[field] = _bytes32(payload[field], field)
    for field in U64_FIELDS.intersection(obj):
        _uint(obj[field], MAX_U64, field)
    for field in U64_FIELDS.intersection(payload):
        _uint(payload[field], MAX_U64, field)
    for field in U128_FIELDS.intersection(payload):
        _uint(payload[field], MAX_U128, field)
    for field in ID_FIELDS.intersection(payload):
        normalized = _bytes32(payload[field], field)
        allowed = {item.lower() for item in catalogs.get(field, set())}
        if normalized not in allowed:
            raise BridgeRejected(f"{field}: symbolic ID not in deterministic catalog")
        payload[field] = normalized

    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return obj, canonical


@dataclass(frozen=True)
class MockAgent:
    recorded_output: str

    def propose(self, _: str) -> str:
        return self.recorded_output

