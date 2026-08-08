# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Notboatanchor Labs LLC; Python adaptation 2026 Mohammed Messaoudene
"""Run the 23 published SEP-3004 C-REC-1..7 vectors in Python.

Fixture values, identifiers and expected dispositions are retained from the
Apache-2.0 vector set pinned in ``UPSTREAM_PINS.json``.  The evaluator is the
independent Python implementation in ``sep3004_cleanroom.py``.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Callable

from sep3004_cleanroom import (
    Sep3004Error,
    canonical_preimage,
    compute_event_hash,
    validate_extensions,
    validate_manifest,
    validate_skeleton,
    verify_chain_segment,
    verify_record,
)

KAT_HASH_CG = "d494769c1ae442ea88dd190068747abf63c0568a3b856f85791b1a50a99d48b4"
KAT_HASH_2X = "f733fed9cc757165f810b778e4baba1f51a45504988e937707aaab4361b2f064"
SID = "55555555-5555-5555-5555-555555555555"
PRINCIPAL = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
NINES = "99999999-9999-9999-9999-999999999999"


def seal(body: dict[str, Any]) -> dict[str, Any]:
    return {**copy.deepcopy(body), "event_hash": compute_event_hash(body)}


REC1 = seal(
    {
        "event_id": NINES,
        "occurred_at": "2026-06-06T12:00:00.000Z",
        "principal_id": PRINCIPAL,
        "event_type": "tool_call",
        "tool_name": "export",
        "outcome": "deferred",
        "previous_hash": None,
        "extensions": {
            "caller-governance": {
                "session_id": SID,
                "invoked_by_principal_id": None,
                "purpose_declared": "reconcile June invoices",
                "flagged": False,
            }
        },
    }
)
REC2 = seal(
    {
        "event_id": "22222222-2222-2222-2222-222222222222",
        "occurred_at": "2026-06-06T12:00:01.000Z",
        "principal_id": PRINCIPAL,
        "event_type": "tool_call",
        "tool_name": "export",
        "outcome": "allowed",
        "previous_hash": REC1["event_hash"],
        "extensions": {
            "caller-governance": {
                "session_id": SID,
                "invoked_by_principal_id": None,
                "purpose_declared": "bulk export",
                "flagged": True,
            }
        },
    }
)
REC_BOTH = seal(
    {
        "event_id": NINES,
        "occurred_at": "2026-06-06T12:00:00.000Z",
        "principal_id": PRINCIPAL,
        "event_type": "tool_call",
        "tool_name": "export",
        "outcome": "deferred",
        "previous_hash": None,
        "extensions": {
            "caller-governance": {
                "flagged": False,
                "invoked_by_principal_id": None,
                "purpose_declared": "reconcile June invoices",
                "session_id": SID,
            },
            "runtime-security": {
                "drift_status": "confirmed",
                "evidence_hash": "sha256:b2c547e2c8f17eafc72ef5c2d4d7b6b4d0f7437ab52bae573a9af14ff5e2d9be",
                "policy_id": "example.org/runtime-drift@3",
                "quarantine_decision": "quarantine",
                "severity": "high",
            },
        },
    }
)
REC_RS = seal(
    {
        "event_id": "33333333-3333-3333-3333-333333333333",
        "occurred_at": "2026-06-06T12:00:02.000Z",
        "principal_id": PRINCIPAL,
        "event_type": "policy_evaluation",
        "tool_name": "export",
        "outcome": "allowed",
        "previous_hash": REC1["event_hash"],
        "extensions": {
            "runtime-security": {
                "drift_status": "observed",
                "severity": "medium",
                "quarantine_decision": "release",
                "policy_id": "example.org/runtime-drift@3",
            }
        },
    }
)
MANIFEST_GOOD = {
    "storage_mechanism": "revoked-dml-rls",
    "chain_algorithm": "sha-256",
    "canonical_form_version": "gif-audit/2",
    "verification_procedure_ref": "https://github.com/notboatanchor/gif (conformance/)",
}


@dataclass(frozen=True)
class Vector:
    id: str
    requirement: str
    title: str
    expect: str
    evaluate: Callable[[], bool]


def _no_failures(function: Callable[..., list[str]], *args: Any) -> bool:
    try:
        return not function(*args)
    except Sep3004Error:
        return False


def _canonical(record: dict[str, Any]) -> bytes | None:
    try:
        return canonical_preimage(record)
    except Sep3004Error:
        return None


def _missing(
    record: dict[str, Any], field: str, validator: Callable[..., list[str]]
) -> bool:
    candidate = copy.deepcopy(record)
    del candidate[field]
    return _no_failures(validator, candidate)


def _missing_caller_field(field: str) -> bool:
    candidate = copy.deepcopy(REC1)
    del candidate["extensions"]["caller-governance"][field]
    return _no_failures(validate_extensions, candidate)


def _unknown_extension() -> bool:
    candidate = copy.deepcopy(REC1)
    candidate["extensions"]["not-a-real-extension"] = {"foo": "bar"}
    return _no_failures(validate_extensions, candidate)


def _reordered_matches() -> bool:
    reordered = {
        "event_hash": REC1["event_hash"],
        "previous_hash": REC1["previous_hash"],
        "outcome": REC1["outcome"],
        "tool_name": REC1["tool_name"],
        "event_type": REC1["event_type"],
        "principal_id": REC1["principal_id"],
        "occurred_at": REC1["occurred_at"],
        "event_id": REC1["event_id"],
        "extensions": {
            "caller-governance": {
                "flagged": False,
                "purpose_declared": "reconcile June invoices",
                "invoked_by_principal_id": None,
                "session_id": SID,
            }
        },
    }
    return _canonical(REC1) == _canonical(reordered)


def _canonical_diff(path: tuple[str, ...], value: Any) -> bool:
    candidate = copy.deepcopy(REC1)
    target: dict[str, Any] = candidate
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return _canonical(REC1) != _canonical(candidate)


def _normalization_matches() -> bool:
    nfc = copy.deepcopy(REC1)
    nfd = copy.deepcopy(REC1)
    nfc["extensions"]["caller-governance"]["purpose_declared"] = "café audit"
    nfd["extensions"]["caller-governance"]["purpose_declared"] = "café audit "
    return _canonical(nfc) == _canonical(nfd)


def _null_differs_from_empty() -> bool:
    null_tool = copy.deepcopy(REC1)
    empty_tool = copy.deepcopy(REC1)
    null_tool["tool_name"] = None
    empty_tool["tool_name"] = ""
    return _canonical(null_tool) != _canonical(empty_tool)


def _control_character_accepted() -> bool:
    candidate = copy.deepcopy(REC1)
    candidate["extensions"]["caller-governance"]["purpose_declared"] = "line1\nline2"
    return _no_failures(verify_record, candidate)


def _kat() -> bool:
    return (
        compute_event_hash(REC1) == KAT_HASH_CG
        and compute_event_hash(REC_BOTH) == KAT_HASH_2X
    )


def _tampered_chain(path: tuple[str, ...], value: Any) -> bool:
    chain = [copy.deepcopy(REC1), copy.deepcopy(REC2)]
    target: dict[str, Any] = chain[0]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return _no_failures(verify_chain_segment, chain)


def _emission_complete() -> bool:
    required = [
        "session_start",
        "session_close",
        "session_expired",
        "session_rejected_closed",
    ]
    emitted = [
        {
            "event_type": event_type,
            "extensions": {"caller-governance": {"session_id": SID}},
        }
        for event_type in required
    ]
    return all(
        any(
            record["event_type"] == event_type
            and record["extensions"]["caller-governance"].get("session_id")
            for record in emitted
        )
        for event_type in required
    )


def _runtime_tamper() -> bool:
    chain = [copy.deepcopy(REC1), copy.deepcopy(REC_RS)]
    chain[1]["extensions"]["runtime-security"]["severity"] = "low"
    return _no_failures(verify_chain_segment, chain)


def _two_extension_tamper() -> bool:
    candidate = copy.deepcopy(REC_BOTH)
    candidate["extensions"]["runtime-security"]["severity"] = "low"
    return _no_failures(verify_record, candidate)


VECTORS = (
    Vector(
        "V-REC1-good",
        "C-REC-1",
        "complete core and extensions",
        "conformant",
        lambda: _no_failures(validate_skeleton, REC1),
    ),
    Vector(
        "V-REC1-missing-core",
        "C-REC-1",
        "missing previous_hash",
        "nonconformant",
        lambda: _missing(REC1, "previous_hash", validate_skeleton),
    ),
    Vector(
        "V-REC1-missing-extensions",
        "C-REC-1",
        "missing extensions",
        "nonconformant",
        lambda: _missing(REC1, "extensions", validate_skeleton),
    ),
    Vector(
        "V-REC1-extension-required-field",
        "C-REC-1",
        "missing purpose_declared",
        "nonconformant",
        lambda: _missing_caller_field("purpose_declared"),
    ),
    Vector(
        "V-REC1-unregistered-extension",
        "C-REC-1",
        "unregistered extension",
        "nonconformant",
        _unknown_extension,
    ),
    Vector(
        "V-REC2-determinism",
        "C-REC-2",
        "key-order independence",
        "conformant",
        _reordered_matches,
    ),
    Vector(
        "V-REC2-injective-core",
        "C-REC-2",
        "core-field injectivity",
        "conformant",
        lambda: _canonical_diff(("outcome",), "denied"),
    ),
    Vector(
        "V-REC2-injective-extension",
        "C-REC-2",
        "extension-field injectivity",
        "conformant",
        lambda: _canonical_diff(
            ("extensions", "caller-governance", "purpose_declared"), "exfiltration"
        ),
    ),
    Vector(
        "V-REC2-null-vs-empty",
        "C-REC-2",
        "null differs from empty",
        "conformant",
        _null_differs_from_empty,
    ),
    Vector(
        "V-REC2-normalization",
        "C-REC-2",
        "NFC and U+0020 trim",
        "conformant",
        _normalization_matches,
    ),
    Vector(
        "V-REC2-control-char",
        "C-REC-2",
        "control character rejection",
        "nonconformant",
        _control_character_accepted,
    ),
    Vector("V-REC3-kat", "C-REC-3", "single and two-extension KAT", "conformant", _kat),
    Vector(
        "V-REC4-good-chain",
        "C-REC-4",
        "valid chain",
        "conformant",
        lambda: _no_failures(verify_chain_segment, [REC1, REC2]),
    ),
    Vector(
        "V-REC4-tamper-core",
        "C-REC-4",
        "core tamper",
        "nonconformant",
        lambda: _tampered_chain(("outcome",), "denied"),
    ),
    Vector(
        "V-REC4-tamper-purpose",
        "C-REC-4",
        "purpose tamper",
        "nonconformant",
        lambda: _tampered_chain(
            ("extensions", "caller-governance", "purpose_declared"),
            "authorized maintenance",
        ),
    ),
    Vector(
        "V-REC4-delete-record",
        "C-REC-4",
        "head deletion",
        "nonconformant",
        lambda: _no_failures(verify_chain_segment, [copy.deepcopy(REC2)]),
    ),
    Vector(
        "V-REC5-emission",
        "C-REC-5",
        "required events emitted",
        "conformant",
        _emission_complete,
    ),
    Vector(
        "V-REC6-mixed-extension-chain",
        "C-REC-6",
        "mixed extension chain",
        "conformant",
        lambda: _no_failures(verify_chain_segment, [REC1, REC_RS]),
    ),
    Vector(
        "V-REC6-extension-fields-chained",
        "C-REC-6",
        "runtime field tamper",
        "nonconformant",
        _runtime_tamper,
    ),
    Vector(
        "V-REC6-two-extension-record",
        "C-REC-6",
        "two-extension record",
        "conformant",
        lambda: _no_failures(verify_record, REC_BOTH),
    ),
    Vector(
        "V-REC6-two-extension-tamper",
        "C-REC-6",
        "two-extension tamper",
        "nonconformant",
        _two_extension_tamper,
    ),
    Vector(
        "V-REC7-manifest-good",
        "C-REC-7",
        "structured manifest",
        "conformant",
        lambda: _no_failures(validate_manifest, MANIFEST_GOOD),
    ),
    Vector(
        "V-REC7-manifest-bare",
        "C-REC-7",
        "bare manifest",
        "nonconformant",
        lambda: _no_failures(validate_manifest, {}),
    ),
)


def run_vectors() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for vector in VECTORS:
        observed_conformant = bool(vector.evaluate())
        observed = "conformant" if observed_conformant else "nonconformant"
        results.append(
            {
                "id": vector.id,
                "requirement": vector.requirement,
                "title": vector.title,
                "expected": vector.expect,
                "observed": observed,
                "pass": observed == vector.expect,
            }
        )
    passed = sum(item["pass"] for item in results)
    return {
        "status": "PASS" if passed == len(results) else "FAIL",
        "passed": passed,
        "failed": len(results) - passed,
        "total": len(results),
        "kat": {"expected": KAT_HASH_2X, "observed": compute_event_hash(REC_BOTH)},
        "results": results,
    }


def main() -> int:
    report = run_vectors()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
