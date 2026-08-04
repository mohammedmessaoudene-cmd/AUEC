# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import hashlib
import time
from copy import deepcopy
from typing import Any

from .canonical import canonical_json_bytes, canonical_json_text, digest_json, sha256_bytes
from .errors import AUECError
from .model import CLASS_RANK, PURE_OPS, ValidatedManifest, classification_max, default_host_policy as _default_policy, validate_manifest


def default_host_policy() -> dict[str, Any]:
    return _default_policy()


def _json_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise AUECError("E_POINTER", "JSON pointer must be empty or start with slash")
    current = value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise AUECError("E_POINTER", "JSON pointer member is absent")
            current = current[token]
        elif isinstance(current, list):
            if token == "-" or not token.isdigit():
                raise AUECError("E_POINTER", "invalid array pointer")
            index = int(token, 10)
            if index >= len(current):
                raise AUECError("E_POINTER", "array pointer is out of range")
            current = current[index]
        else:
            raise AUECError("E_POINTER", "JSON pointer traverses a scalar")
    return current


def _require(value: Any, typ: type, name: str) -> Any:
    if typ is int:
        if not isinstance(value, int) or isinstance(value, bool):
            raise AUECError("E_INPUT", f"{name} must be an integer")
        return value
    if not isinstance(value, typ):
        raise AUECError("E_INPUT", f"{name} has invalid type")
    return value


def _replace_literal(text: str, needles: list[str], replacement: str) -> str:
    ordered = sorted(set(needles), key=lambda item: (-len(item), item.encode("utf-16-be")))
    if any(item == "" for item in ordered):
        raise AUECError("E_PARAMS", "empty redaction needle is forbidden")
    out: list[str] = []
    index = 0
    while index < len(text):
        match = next((needle for needle in ordered if text.startswith(needle, index)), None)
        if match is None:
            out.append(text[index])
            index += 1
        else:
            out.append(replacement)
            index += len(match)
    return "".join(out)


def _execute_op(op: str, inputs: dict[str, Any], params: dict[str, Any]) -> Any:
    if op == "core.identity":
        if set(inputs) != {"value"} or params:
            raise AUECError("E_SIGNATURE", "core.identity expects value and no params")
        return deepcopy(inputs["value"])
    if op == "hash.sha256":
        if set(inputs) != {"value"} or params:
            raise AUECError("E_SIGNATURE", "hash.sha256 expects value and no params")
        return {"algorithm": "sha-256", "digest": digest_json(inputs["value"])}
    if op == "text.length":
        if set(inputs) != {"text"} or params:
            raise AUECError("E_SIGNATURE", "text.length expects text and no params")
        text = _require(inputs["text"], str, "text")
        return {"unicodeScalars": len(text), "utf8Bytes": len(text.encode("utf-8"))}
    if op == "text.concat":
        if set(inputs) != {"items"} or set(params) - {"separator"}:
            raise AUECError("E_SIGNATURE", "text.concat signature mismatch")
        items = _require(inputs["items"], list, "items")
        if any(not isinstance(item, str) for item in items):
            raise AUECError("E_INPUT", "concat items must be strings")
        separator = params.get("separator", "")
        _require(separator, str, "separator")
        return separator.join(items)
    if op == "text.search_literal":
        if set(inputs) != {"text"} or set(params) != {"needles"}:
            raise AUECError("E_SIGNATURE", "text.search_literal signature mismatch")
        text = _require(inputs["text"], str, "text")
        needles = _require(params["needles"], list, "needles")
        if len(needles) > 256 or any(not isinstance(item, str) or item == "" for item in needles):
            raise AUECError("E_PARAMS", "needles must be bounded non-empty strings")
        matches: list[dict[str, Any]] = []
        for needle in needles:
            start = 0
            while True:
                index = text.find(needle, start)
                if index < 0:
                    break
                matches.append({"needle": needle, "startScalar": index, "endScalar": index + len(needle)})
                start = index + max(1, len(needle))
        matches.sort(key=lambda item: (item["startScalar"], item["endScalar"], item["needle"].encode("utf-16-be")))
        return {"matches": matches, "total": len(matches)}
    if op == "text.redact_literal":
        if set(inputs) != {"text"} or set(params) - {"needles", "replacement"} or "needles" not in params:
            raise AUECError("E_SIGNATURE", "text.redact_literal signature mismatch")
        text = _require(inputs["text"], str, "text")
        needles = _require(params["needles"], list, "needles")
        replacement = params.get("replacement", "[REDACTED]")
        _require(replacement, str, "replacement")
        if len(needles) > 256 or any(not isinstance(item, str) for item in needles):
            raise AUECError("E_PARAMS", "invalid redaction needles")
        return _replace_literal(text, needles, replacement)
    if op == "json.project":
        if set(inputs) != {"value"} or set(params) != {"pointers"}:
            raise AUECError("E_SIGNATURE", "json.project signature mismatch")
        pointers = _require(params["pointers"], list, "pointers")
        if len(pointers) > 256 or any(not isinstance(item, str) for item in pointers) or len(pointers) != len(set(pointers)):
            raise AUECError("E_PARAMS", "pointers must be unique strings")
        return {pointer: deepcopy(_json_pointer(inputs["value"], pointer)) for pointer in pointers}
    if op == "list.deduplicate":
        if set(inputs) != {"items"} or params:
            raise AUECError("E_SIGNATURE", "list.deduplicate expects items and no params")
        items = _require(inputs["items"], list, "items")
        seen: set[str] = set()
        result: list[Any] = []
        for item in items:
            key = canonical_json_text(item)
            if key not in seen:
                seen.add(key)
                result.append(deepcopy(item))
        return result
    if op == "math.sum_safeint":
        if set(inputs) != {"values"} or params:
            raise AUECError("E_SIGNATURE", "math.sum_safeint expects values and no params")
        values = _require(inputs["values"], list, "values")
        total = 0
        for value in values:
            _require(value, int, "sum value")
            total += value
            if total < -9_007_199_254_740_991 or total > 9_007_199_254_740_991:
                raise AUECError("E_INTEGER_RANGE", "sum exceeds the interoperable safe-integer range")
        return total
    raise AUECError("E_OPERATION", "operation is not implemented")


def _resolve_expr(expr: dict[str, Any], resources: dict[str, dict[str, Any]], outputs: dict[str, dict[str, Any]]) -> tuple[Any, str]:
    if set(expr) == {"literal"}:
        return deepcopy(expr["literal"]), "public"
    if set(expr) == {"resource"}:
        resource_id = expr["resource"]
        if resource_id not in resources:
            raise AUECError("E_REFERENCE", "resource reference does not exist")
        resource = resources[resource_id]
        return deepcopy(resource["value"]), resource["classification"]
    if set(expr) in ({"node"}, {"node", "pointer"}):
        node_id = expr["node"]
        if node_id not in outputs:
            raise AUECError("E_REFERENCE", "node result is not available")
        envelope = outputs[node_id]
        value = envelope["value"]
        if "pointer" in expr:
            value = _json_pointer(value, expr["pointer"])
        return deepcopy(value), envelope["classification"]
    raise AUECError("E_SCHEMA", "invalid input expression")


def _choose_placement(node: dict[str, Any], policy: dict[str, Any]) -> str:
    permitted = [item for item in node["placement"]["allowed"] if item in policy["allowedPlacements"]]
    if not permitted:
        raise AUECError("E_PLACEMENT", "no effective placement")
    preferred = node["placement"]["preferred"]
    return preferred if preferred in permitted else sorted(permitted)[0]


class UniversalRuntime:
    """Transport-neutral U0 reference runtime with deterministic logical receipts."""

    def __init__(self, host_policy: dict[str, Any] | None = None) -> None:
        self.host_policy = default_host_policy() if host_policy is None else deepcopy(host_policy)

    def execute(self, manifest: dict[str, Any]) -> dict[str, Any]:
        started = time.monotonic_ns()
        try:
            validated = validate_manifest(manifest, self.host_policy)
            return self._execute_validated(validated, started)
        except AUECError as exc:
            manifest_id = manifest.get("manifestId") if isinstance(manifest, dict) and isinstance(manifest.get("manifestId"), str) else None
            result: dict[str, Any] = {
                "auecVersion": "0.1",
                "status": "rejected",
                "error": {"code": exc.info.code},
            }
            if manifest_id is not None:
                result["manifestId"] = manifest_id
            return result

    def _execute_validated(self, validated: ValidatedManifest, started_ns: int) -> dict[str, Any]:
        manifest = validated.raw
        policy = validated.effective_policy
        manifest_digest = digest_json(manifest)
        outputs: dict[str, dict[str, Any]] = {}
        receipts: list[dict[str, Any]] = []
        previous = "sha256:" + "0" * 64
        total_output = 0

        for sequence, node_id in enumerate(validated.order, start=1):
            elapsed_ms = (time.monotonic_ns() - started_ns) // 1_000_000
            if elapsed_ms > policy["budgets"]["maxWallMs"]:
                raise AUECError("E_WALL_BUDGET", "wall-time budget exceeded")
            node = validated.node_by_id[node_id]
            resolved: dict[str, Any] = {}
            input_classes: list[str] = []
            for name, expr in node["inputs"].items():
                value, classification = _resolve_expr(expr, manifest["resources"], outputs)
                resolved[name] = value
                input_classes.append(classification)
            inherited = classification_max(input_classes)
            declared = node["output"]["classification"]
            if CLASS_RANK[declared] < CLASS_RANK[inherited]:
                raise AUECError("E_CLASSIFICATION_DOWNGRADE", "output classification is below input classification")
            value = _execute_op(node["op"], resolved, node["params"])
            output = {
                "epistemic": node["output"]["epistemic"],
                "classification": declared,
                "verified": True,
                "value": value,
            }
            encoded = canonical_json_bytes(output)
            total_output += len(encoded)
            if total_output > policy["budgets"]["maxOutputBytes"]:
                raise AUECError("E_OUTPUT_BUDGET", "cumulative output budget exceeded")
            placement = _choose_placement(node, policy)
            body = {
                "auecVersion": "0.1",
                "manifestDigest": manifest_digest,
                "manifestId": manifest["manifestId"],
                "sequence": sequence,
                "nodeId": node_id,
                "op": node["op"],
                "effect": "pure",
                "placement": placement,
                "inputDigest": digest_json(resolved),
                "outputDigest": digest_json(output),
                "previousReceiptDigest": previous,
            }
            receipt_digest = digest_json(body)
            receipt = {**body, "receiptDigest": receipt_digest}
            previous = receipt_digest
            outputs[node_id] = output
            receipts.append(receipt)

        exports: dict[str, Any] = {}
        max_export_rank = CLASS_RANK[policy["maxExportClassification"]]
        for node_id in validated.order:
            node = validated.node_by_id[node_id]
            if not node["output"]["export"]:
                continue
            output = outputs[node_id]
            if CLASS_RANK[output["classification"]] > max_export_rank:
                raise AUECError("E_EGRESS_CLASSIFICATION", "output classification exceeds host egress policy")
            if output["epistemic"] in {"claim", "hypothesis"} and not policy["allowClaimExport"]:
                raise AUECError("E_EPISTEMIC_EGRESS", "claim or hypothesis export is forbidden")
            if output["classification"] == "secret" or output["epistemic"] == "secret":
                raise AUECError("E_SECRET_EGRESS", "secret output cannot be exported")
            exports[node_id] = output

        terminal_body = {
            "auecVersion": "0.1",
            "manifestDigest": manifest_digest,
            "manifestId": manifest["manifestId"],
            "status": "succeeded",
            "receiptCount": len(receipts),
            "lastReceiptDigest": previous,
            "exportsDigest": digest_json(exports),
        }
        terminal_digest = digest_json(terminal_body)
        return {
            **terminal_body,
            "terminalDigest": terminal_digest,
            "exports": exports,
            "receipts": receipts,
        }
