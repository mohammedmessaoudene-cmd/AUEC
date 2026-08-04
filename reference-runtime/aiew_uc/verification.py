# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

from typing import Any

from .canonical import digest_json
from .errors import AUECError


def verify_result(result: dict[str, Any], manifest: dict[str, Any] | None = None) -> dict[str, int]:
    if not isinstance(result, dict) or result.get("auecVersion") != "0.1" or result.get("status") != "succeeded":
        raise AUECError("E_VERIFY", "result is not a successful AUEC result")
    if manifest is not None:
        if result.get("manifestId") != manifest.get("manifestId") or result.get("manifestDigest") != digest_json(manifest):
            raise AUECError("E_VERIFY_MANIFEST", "result does not match manifest")
    receipts = result.get("receipts")
    exports = result.get("exports")
    if not isinstance(receipts, list) or not isinstance(exports, dict):
        raise AUECError("E_VERIFY", "result has invalid receipt or export structure")
    previous = "sha256:" + "0" * 64
    by_node: dict[str, dict[str, Any]] = {}
    for index, receipt in enumerate(receipts, start=1):
        if not isinstance(receipt, dict):
            raise AUECError("E_VERIFY_RECEIPT", "receipt must be an object")
        if receipt.get("sequence") != index or receipt.get("previousReceiptDigest") != previous:
            raise AUECError("E_VERIFY_RECEIPT", "receipt chain order is invalid")
        body = {key: value for key, value in receipt.items() if key != "receiptDigest"}
        expected = digest_json(body)
        if receipt.get("receiptDigest") != expected:
            raise AUECError("E_VERIFY_RECEIPT", "receipt digest mismatch")
        if receipt.get("manifestId") != result.get("manifestId") or receipt.get("manifestDigest") != result.get("manifestDigest"):
            raise AUECError("E_VERIFY_RECEIPT", "receipt manifest identity mismatch")
        node_id = receipt.get("nodeId")
        if not isinstance(node_id, str) or node_id in by_node:
            raise AUECError("E_VERIFY_RECEIPT", "receipt node identity is invalid")
        by_node[node_id] = receipt
        previous = expected
    if result.get("receiptCount") != len(receipts) or result.get("lastReceiptDigest") != previous:
        raise AUECError("E_VERIFY_RECEIPT", "terminal receipt counters mismatch")
    if result.get("exportsDigest") != digest_json(exports):
        raise AUECError("E_VERIFY_EXPORT", "exports digest mismatch")
    for node_id, envelope in exports.items():
        if node_id not in by_node or by_node[node_id].get("outputDigest") != digest_json(envelope):
            raise AUECError("E_VERIFY_EXPORT", "export does not match node receipt")
    terminal_body = {
        "auecVersion": "0.1",
        "manifestDigest": result.get("manifestDigest"),
        "manifestId": result.get("manifestId"),
        "status": "succeeded",
        "receiptCount": len(receipts),
        "lastReceiptDigest": previous,
        "exportsDigest": digest_json(exports),
    }
    if result.get("terminalDigest") != digest_json(terminal_body):
        raise AUECError("E_VERIFY_TERMINAL", "terminal digest mismatch")
    return {"receipts": len(receipts), "exports": len(exports)}
