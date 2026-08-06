# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import heapq
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .canonical import canonical_json_bytes, ensure_value
from .errors import AUECError

VERSION = "0.1"
PROFILE_U0 = "U0-pure"
ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
CLASSIFICATIONS = ("public", "internal", "confidential", "secret")
CLASS_RANK = {name: index for index, name in enumerate(CLASSIFICATIONS)}
EPISTEMIC = {"fact", "claim", "hypothesis", "artifact", "secret"}
PLACEMENTS = {"local", "edge", "cloud"}
PURE_OPS = {
    "core.identity",
    "hash.sha256",
    "json.project",
    "list.deduplicate",
    "math.sum_safeint",
    "text.concat",
    "text.length",
    "text.redact_literal",
    "text.search_literal",
}


@dataclass(frozen=True)
class ValidatedManifest:
    raw: dict[str, Any]
    node_by_id: dict[str, dict[str, Any]]
    order: tuple[str, ...]
    effective_policy: dict[str, Any]


def _exact_int(value: Any, name: str, minimum: int, maximum: int) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > maximum
    ):
        raise AUECError("E_SCHEMA", f"{name} must be an integer in range")
    return value


def _exact_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise AUECError("E_SCHEMA", f"{name} must be boolean")
    return value


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AUECError("E_SCHEMA", f"{name} must be an object")
    return value


def _array(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise AUECError("E_SCHEMA", f"{name} must be an array")
    return value


def _keys(
    obj: Mapping[str, Any], *, required: set[str], allowed: set[str], name: str
) -> None:
    missing = required - set(obj)
    extra = set(obj) - allowed
    if missing:
        raise AUECError("E_SCHEMA", f"{name} missing required fields")
    if extra:
        raise AUECError("E_SCHEMA", f"{name} contains unknown fields")


def _classification(value: Any, name: str) -> str:
    if value not in CLASS_RANK:
        raise AUECError("E_SCHEMA", f"{name} has invalid classification")
    return str(value)


def _id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise AUECError("E_SCHEMA", f"{name} has invalid identifier")
    return value


def default_host_policy() -> dict[str, Any]:
    return {
        "policyVersion": "0.1",
        "allowedProfiles": [PROFILE_U0],
        "allowedOps": sorted(PURE_OPS),
        "allowedEffects": ["pure"],
        "allowedPlacements": ["local"],
        "maxExportClassification": "internal",
        "allowClaimExport": False,
        "budgets": {
            "maxNodes": 256,
            "maxOutputBytes": 1_048_576,
            "maxWallMs": 10_000,
            "maxManifestBytes": 2_097_152,
        },
    }


def validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    policy = _object(policy, "policy")
    _keys(
        policy,
        required={
            "policyVersion",
            "allowedProfiles",
            "allowedOps",
            "allowedEffects",
            "allowedPlacements",
            "maxExportClassification",
            "allowClaimExport",
            "budgets",
        },
        allowed={
            "policyVersion",
            "allowedProfiles",
            "allowedOps",
            "allowedEffects",
            "allowedPlacements",
            "maxExportClassification",
            "allowClaimExport",
            "budgets",
        },
        name="policy",
    )
    if policy["policyVersion"] != VERSION:
        raise AUECError("E_POLICY_VERSION", "unsupported policy version")
    profiles = _array(policy["allowedProfiles"], "allowedProfiles")
    if not profiles or any(item != PROFILE_U0 for item in profiles):
        raise AUECError("E_POLICY", "unsupported profile in policy")
    ops = _array(policy["allowedOps"], "allowedOps")
    if any(not isinstance(item, str) or item not in PURE_OPS for item in ops) or len(
        ops
    ) != len(set(ops)):
        raise AUECError("E_POLICY", "invalid allowedOps")
    effects = _array(policy["allowedEffects"], "allowedEffects")
    if any(item != "pure" for item in effects) or len(effects) != len(set(effects)):
        raise AUECError("E_POLICY", "U0 permits only pure effects")
    placements = _array(policy["allowedPlacements"], "allowedPlacements")
    if any(item not in PLACEMENTS for item in placements) or len(placements) != len(
        set(placements)
    ):
        raise AUECError("E_POLICY", "invalid placements")
    _classification(policy["maxExportClassification"], "maxExportClassification")
    _exact_bool(policy["allowClaimExport"], "allowClaimExport")
    budgets = _object(policy["budgets"], "policy budgets")
    _keys(
        budgets,
        required={"maxNodes", "maxOutputBytes", "maxWallMs", "maxManifestBytes"},
        allowed={"maxNodes", "maxOutputBytes", "maxWallMs", "maxManifestBytes"},
        name="policy budgets",
    )
    _exact_int(budgets["maxNodes"], "maxNodes", 1, 10_000)
    _exact_int(budgets["maxOutputBytes"], "maxOutputBytes", 1, 2**30)
    _exact_int(budgets["maxWallMs"], "maxWallMs", 1, 86_400_000)
    _exact_int(budgets["maxManifestBytes"], "maxManifestBytes", 1, 16_777_216)
    ensure_value(policy, max_depth=32, max_items=100_000)
    return policy


def _extract_node_refs(expr: Any, refs: set[str]) -> None:
    if isinstance(expr, dict):
        if set(expr) == {"node"}:
            refs.add(_id(expr["node"], "node reference"))
            return
        if set(expr) == {"node", "pointer"}:
            refs.add(_id(expr["node"], "node reference"))
            if not isinstance(expr["pointer"], str):
                raise AUECError("E_SCHEMA", "pointer must be a string")
            return
        if set(expr) == {"resource"}:
            _id(expr["resource"], "resource reference")
            return
        if set(expr) == {"literal"}:
            ensure_value(expr["literal"], max_depth=32, max_items=100_000)
            return
        raise AUECError("E_SCHEMA", "input expression has invalid shape")
    raise AUECError("E_SCHEMA", "input expression must be an object")


def _topological(
    node_by_id: dict[str, dict[str, Any]], refs_by_node: dict[str, set[str]]
) -> tuple[str, ...]:
    indegree = {node_id: 0 for node_id in node_by_id}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_by_id}
    for node_id, refs in refs_by_node.items():
        for ref in refs:
            if ref not in node_by_id:
                raise AUECError("E_REFERENCE", "node reference does not exist")
            indegree[node_id] += 1
            outgoing[ref].append(node_id)
    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    heapq.heapify(queue)
    order: list[str] = []
    while queue:
        current = heapq.heappop(queue)
        order.append(current)
        for child in sorted(outgoing[current]):
            indegree[child] -= 1
            if indegree[child] == 0:
                heapq.heappush(queue, child)
    if len(order) != len(node_by_id):
        raise AUECError("E_CYCLE", "manifest graph contains a cycle")
    return tuple(order)


def validate_manifest(
    manifest: dict[str, Any], host_policy: dict[str, Any] | None = None
) -> ValidatedManifest:
    ensure_value(manifest, max_depth=64, max_items=1_000_000)
    policy = validate_policy(
        default_host_policy() if host_policy is None else host_policy
    )
    _keys(
        manifest,
        required={
            "auecVersion",
            "manifestId",
            "profile",
            "resources",
            "budgets",
            "nodes",
        },
        allowed={
            "auecVersion",
            "manifestId",
            "profile",
            "resources",
            "budgets",
            "nodes",
            "metadata",
        },
        name="manifest",
    )
    if manifest["auecVersion"] != VERSION:
        raise AUECError("E_VERSION", "unsupported AUEC version")
    _id(manifest["manifestId"], "manifestId")
    if (
        manifest["profile"] != PROFILE_U0
        or manifest["profile"] not in policy["allowedProfiles"]
    ):
        raise AUECError("E_PROFILE", "profile is not allowed")
    if len(canonical_json_bytes(manifest)) > policy["budgets"]["maxManifestBytes"]:
        raise AUECError("E_MANIFEST_SIZE", "manifest exceeds host byte bound")

    budgets = _object(manifest["budgets"], "budgets")
    _keys(
        budgets,
        required={"maxNodes", "maxOutputBytes", "maxWallMs"},
        allowed={"maxNodes", "maxOutputBytes", "maxWallMs"},
        name="budgets",
    )
    requested_nodes = _exact_int(budgets["maxNodes"], "maxNodes", 1, 10_000)
    requested_output = _exact_int(budgets["maxOutputBytes"], "maxOutputBytes", 1, 2**30)
    requested_wall = _exact_int(budgets["maxWallMs"], "maxWallMs", 1, 86_400_000)
    effective = {
        **policy,
        "budgets": {
            "maxNodes": min(requested_nodes, policy["budgets"]["maxNodes"]),
            "maxOutputBytes": min(
                requested_output, policy["budgets"]["maxOutputBytes"]
            ),
            "maxWallMs": min(requested_wall, policy["budgets"]["maxWallMs"]),
            "maxManifestBytes": policy["budgets"]["maxManifestBytes"],
        },
    }

    resources = _object(manifest["resources"], "resources")
    if len(resources) > 1_000:
        raise AUECError("E_RESOURCE_LIMIT", "too many resources")
    for name, resource in resources.items():
        _id(name, "resource id")
        resource = _object(resource, "resource")
        _keys(
            resource,
            required={"classification", "value"},
            allowed={"classification", "value", "mediaType"},
            name="resource",
        )
        _classification(resource["classification"], "resource classification")
        if "mediaType" in resource and (
            not isinstance(resource["mediaType"], str)
            or len(resource["mediaType"]) > 128
        ):
            raise AUECError("E_SCHEMA", "invalid resource mediaType")
        ensure_value(resource["value"], max_depth=32, max_items=100_000)

    nodes = _array(manifest["nodes"], "nodes")
    if not nodes or len(nodes) > effective["budgets"]["maxNodes"]:
        raise AUECError("E_NODE_BUDGET", "node count exceeds effective budget")
    node_by_id: dict[str, dict[str, Any]] = {}
    refs_by_node: dict[str, set[str]] = {}
    for raw_node in nodes:
        node = _object(raw_node, "node")
        _keys(
            node,
            required={"id", "op", "inputs", "params", "effect", "placement", "output"},
            allowed={"id", "op", "inputs", "params", "effect", "placement", "output"},
            name="node",
        )
        node_id = _id(node["id"], "node id")
        if node_id in node_by_id:
            raise AUECError("E_DUPLICATE_ID", "duplicate node id")
        op = node["op"]
        if (
            not isinstance(op, str)
            or op not in PURE_OPS
            or op not in policy["allowedOps"]
        ):
            raise AUECError("E_OPERATION", "operation is unsupported or forbidden")
        if node["effect"] != "pure" or node["effect"] not in policy["allowedEffects"]:
            raise AUECError("E_EFFECT", "U0 operation must be pure")
        placement = _object(node["placement"], "placement")
        _keys(
            placement,
            required={"allowed", "preferred"},
            allowed={"allowed", "preferred"},
            name="placement",
        )
        allowed = _array(placement["allowed"], "placement.allowed")
        if (
            not allowed
            or any(item not in PLACEMENTS for item in allowed)
            or len(allowed) != len(set(allowed))
        ):
            raise AUECError("E_PLACEMENT", "invalid placement list")
        if placement["preferred"] not in allowed:
            raise AUECError("E_PLACEMENT", "preferred placement is not allowed")
        if not (set(allowed) & set(policy["allowedPlacements"])):
            raise AUECError("E_PLACEMENT", "no host-permitted placement")
        inputs = _object(node["inputs"], "inputs")
        refs: set[str] = set()
        for input_name, expr in inputs.items():
            _id(input_name, "input name")
            _extract_node_refs(expr, refs)
        params = _object(node["params"], "params")
        ensure_value(params, max_depth=24, max_items=100_000)
        output = _object(node["output"], "output")
        _keys(
            output,
            required={"epistemic", "classification", "export"},
            allowed={"epistemic", "classification", "export"},
            name="output",
        )
        if output["epistemic"] not in EPISTEMIC:
            raise AUECError("E_SCHEMA", "invalid epistemic kind")
        if output["epistemic"] not in {"fact", "artifact"}:
            raise AUECError(
                "E_EPISTEMIC", "deterministic U0 operations emit only fact or artifact"
            )
        _classification(output["classification"], "output classification")
        _exact_bool(output["export"], "output.export")
        node_by_id[node_id] = node
        refs_by_node[node_id] = refs
    order = _topological(node_by_id, refs_by_node)
    return ValidatedManifest(
        raw=manifest, node_by_id=node_by_id, order=order, effective_policy=effective
    )


def classification_max(values: Sequence[str]) -> str:
    if not values:
        return "public"
    return max(values, key=lambda item: CLASS_RANK[item])
