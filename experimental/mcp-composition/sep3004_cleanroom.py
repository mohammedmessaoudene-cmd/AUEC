# SPDX-License-Identifier: Apache-2.0
"""Clean-room Python implementation of the draft SEP-3004 v1 record rules.

The implementation is derived from the normative text at the pinned SEP head,
not from the TypeScript reference implementation.  It deliberately keeps the
current registry separate from AUEC's experimental decision-evidence fields.
Clean-room here describes source provenance, not organizationally independent
validation.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from datetime import datetime
from typing import Any


CORE_FIELDS = {
    "event_id",
    "occurred_at",
    "principal_id",
    "event_type",
    "tool_name",
    "outcome",
    "extensions",
    "previous_hash",
    "event_hash",
}
PROTECTED_CORE_FIELDS = CORE_FIELDS - {"event_hash"}
OUTCOMES = {"allowed", "denied", "deferred", "error"}
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
MAX_STRING_CODE_UNITS = 8192
MAX_DEPTH = 32

CALLER_GOVERNANCE_FIELDS = {
    "purpose_declared",
    "session_id",
    "invoked_by_principal_id",
    "flagged",
    "sources_touched",
    "sensitivity_encountered",
    "output_disposition",
    "human_actor_id",
}
RUNTIME_SECURITY_FIELDS = {
    "drift_status",
    "severity",
    "quarantine_decision",
    "policy_id",
    "evidence_hash",
}
REGISTERED_EXTENSIONS = {"caller-governance", "runtime-security"}


class Sep3004Error(ValueError):
    """Raised when a protected record cannot be represented under draft v1."""


def _utf16_code_units(value: str) -> int:
    try:
        return len(value.encode("utf-16-le")) // 2
    except UnicodeEncodeError as exc:
        raise Sep3004Error("protected string contains an unpaired surrogate") from exc


def normalize_string(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value).strip(" ")
    if any(unicodedata.category(character) == "Cc" for character in normalized):
        raise Sep3004Error("protected string contains a control character")
    if _utf16_code_units(normalized) > MAX_STRING_CODE_UNITS:
        raise Sep3004Error("protected string exceeds 8192 UTF-16 code units")
    return normalized


def _normalize(value: Any, *, depth: int = 0) -> Any:
    if depth > MAX_DEPTH:
        raise Sep3004Error("protected body exceeds the recursion-depth limit")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return normalize_string(value)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise Sep3004Error("protected object keys must be strings")
            result[key] = _normalize(item, depth=depth + 1)
        return result
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        raise Sep3004Error("bare numbers are excluded from protected bodies")
    if isinstance(value, list):
        raise Sep3004Error("arrays are not part of the draft v1 protected profile")
    raise Sep3004Error(f"unsupported protected value: {type(value).__name__}")


def protected_body(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise Sep3004Error("record must be an object")
    missing = PROTECTED_CORE_FIELDS - set(record)
    if missing:
        raise Sep3004Error(f"missing protected core fields: {sorted(missing)}")
    return {key: copy.deepcopy(record[key]) for key in PROTECTED_CORE_FIELDS}


def canonical_preimage(record: dict[str, Any]) -> bytes:
    normalized = _normalize(protected_body(record))
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_event_hash(record: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_preimage(record)).hexdigest()


def _is_string_or_null(value: Any) -> bool:
    return value is None or isinstance(value, str)


def validate_extensions(record: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    extensions = record.get("extensions")
    if not isinstance(extensions, dict) or not extensions:
        return ["extensions must be a non-empty keyed object"]
    unknown = set(extensions) - REGISTERED_EXTENSIONS
    if unknown:
        failures.append(f"unregistered extension types: {sorted(unknown)}")

    caller = extensions.get("caller-governance")
    if caller is not None:
        if not isinstance(caller, dict):
            failures.append("caller-governance must be an object")
        else:
            extra = set(caller) - CALLER_GOVERNANCE_FIELDS
            if extra:
                failures.append(
                    f"unregistered caller-governance fields: {sorted(extra)}"
                )
            if not isinstance(caller.get("purpose_declared"), str):
                failures.append("caller-governance purpose_declared is required")
            for field, value in caller.items():
                if field == "flagged":
                    if not isinstance(value, bool):
                        failures.append("caller-governance flagged must be boolean")
                elif not _is_string_or_null(value):
                    failures.append(f"caller-governance {field} must be string or null")

    runtime = extensions.get("runtime-security")
    if runtime is not None:
        if not isinstance(runtime, dict):
            failures.append("runtime-security must be an object")
        else:
            extra = set(runtime) - RUNTIME_SECURITY_FIELDS
            if extra:
                failures.append(
                    f"unregistered runtime-security fields: {sorted(extra)}"
                )
            required = {
                "drift_status",
                "severity",
                "quarantine_decision",
                "policy_id",
            }
            missing = required - set(runtime)
            if missing:
                failures.append(f"runtime-security missing fields: {sorted(missing)}")
            if any(not isinstance(value, str) for value in runtime.values()):
                failures.append("runtime-security values must all be strings")
            if runtime.get("drift_status") not in {"none", "observed", "confirmed"}:
                failures.append("runtime-security drift_status is invalid")
            if runtime.get("severity") not in {"info", "low", "medium", "high"}:
                failures.append("runtime-security severity is invalid")
            if runtime.get("quarantine_decision") not in {
                "release",
                "hold",
                "quarantine",
            }:
                failures.append("runtime-security quarantine_decision is invalid")
    return failures


def validate_skeleton(record: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if not isinstance(record, dict):
        return ["record must be an object"]
    missing = CORE_FIELDS - set(record)
    if missing:
        failures.append(f"missing core fields: {sorted(missing)}")
        return failures
    for field in ("event_id", "principal_id", "event_type"):
        if not isinstance(record[field], str):
            failures.append(f"{field} must be a string")
    if not _is_string_or_null(record["tool_name"]):
        failures.append("tool_name must be string or null")
    if record["outcome"] not in OUTCOMES:
        failures.append("outcome is outside the closed disposition vocabulary")
    occurred_at = record["occurred_at"]
    if not isinstance(occurred_at, str) or not TIMESTAMP_RE.fullmatch(occurred_at):
        failures.append("occurred_at is not RFC3339 UTC millisecond form")
    else:
        try:
            datetime.strptime(occurred_at, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            failures.append("occurred_at is not a real timestamp")
    previous_hash = record["previous_hash"]
    if previous_hash is not None and (
        not isinstance(previous_hash, str) or not HASH_RE.fullmatch(previous_hash)
    ):
        failures.append("previous_hash must be a SHA-256 hex digest or null")
    event_hash = record["event_hash"]
    if not isinstance(event_hash, str) or not HASH_RE.fullmatch(event_hash):
        failures.append("event_hash must be a SHA-256 hex digest")
    failures.extend(validate_extensions(record))
    try:
        canonical_preimage(record)
    except Sep3004Error as exc:
        failures.append(str(exc))
    return failures


def verify_record(record: dict[str, Any]) -> list[str]:
    failures = validate_skeleton(record)
    if failures:
        return failures
    try:
        computed = compute_event_hash(record)
    except Sep3004Error as exc:
        return [str(exc)]
    if computed != record["event_hash"]:
        failures.append("event_hash does not match the protected body")
    return failures


def verify_chain_segment(records: list[dict[str, Any]]) -> list[str]:
    if not records:
        return ["chain segment is empty"]
    failures: list[str] = []
    for index, record in enumerate(records):
        failures.extend(f"record {index}: {item}" for item in verify_record(record))
        expected = None if index == 0 else records[index - 1].get("event_hash")
        if record.get("previous_hash") != expected:
            failures.append(f"record {index}: previous_hash threading mismatch")
    return failures


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    required = {
        "storage_mechanism",
        "chain_algorithm",
        "canonical_form_version",
        "verification_procedure_ref",
    }
    if not isinstance(manifest, dict):
        return ["attestation manifest must be an object"]
    failures: list[str] = []
    missing = required - set(manifest)
    if missing:
        failures.append(f"attestation manifest missing fields: {sorted(missing)}")
    for field in required & set(manifest):
        if not isinstance(manifest[field], str) or not manifest[field]:
            failures.append(f"attestation manifest {field} must be a non-empty string")
    return failures


def qualify_producer_trust(
    *, authenticated_identity: bool = False, external_anchor_verified: bool = False
) -> str:
    if external_anchor_verified:
        return "externally_anchored"
    if authenticated_identity:
        return "authenticated"
    return "self_attested"
