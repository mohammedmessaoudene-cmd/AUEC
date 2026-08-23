#!/usr/bin/env python3
"""Independent Python oracle for the narrowed AUEC Authority-Delta V2.1 Core."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

PROFILE = "auec-authority-delta-decision-v2_1"
C14N = "auec-authority-delta-c14n-v2_1"
MAX_SAFE = 9007199254740991
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
RFC3339_MS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
LIMITS = {
    "documentBytes": 262144,
    "depth": 64,
    "nodes": 10000,
    "stringBytes": 16384,
    "totalStringBytes": 131072,
    "integerDigits": 16,
    "decimalDigits": 64,
}


class ProfileError(ValueError):
    pass


def fail(code: str):
    raise ProfileError(code)


def utf8_key(value: str):
    return value.encode("utf-8")


def has_lone_surrogate(value: str):
    return any(0xD800 <= ord(char) <= 0xDFFF for char in value)


def validate_string(value: str, state: dict):
    if has_lone_surrogate(value):
        fail("LONE_SURROGATE")
    if value != unicodedata.normalize("NFC", value):
        fail("NON_NFC_STRING")
    size = len(value.encode("utf-8"))
    if size > LIMITS["stringBytes"]:
        fail("LIMIT_STRING_BYTES")
    state["totalStringBytes"] += size
    if state["totalStringBytes"] > LIMITS["totalStringBytes"]:
        fail("LIMIT_TOTAL_STRING_BYTES")


def canonical(value):
    state = {"nodes": 0, "totalStringBytes": 0}

    def walk(item, depth):
        if depth > LIMITS["depth"]:
            fail("LIMIT_DEPTH")
        state["nodes"] += 1
        if state["nodes"] > LIMITS["nodes"]:
            fail("LIMIT_NODES")
        if item is None:
            return "null"
        if isinstance(item, bool):
            return "true" if item else "false"
        if isinstance(item, int):
            if abs(item) > MAX_SAFE:
                fail("UNSAFE_INTEGER")
            return str(item)
        if isinstance(item, float):
            fail("UNSAFE_INTEGER")
        if isinstance(item, str):
            validate_string(item, state)
            return json.dumps(item, ensure_ascii=False, separators=(",", ":"))
        if isinstance(item, list):
            return "[" + ",".join(walk(entry, depth + 1) for entry in item) + "]"
        if isinstance(item, dict):
            for key in item:
                if not isinstance(key, str):
                    fail("UNSUPPORTED_JSON_TYPE")
                validate_string(key, state)
            keys = sorted(item, key=utf8_key)
            return "{" + ",".join(
                json.dumps(key, ensure_ascii=False, separators=(",", ":")) + ":" + walk(item[key], depth + 1)
                for key in keys
            ) + "}"
        fail("UNSUPPORTED_JSON_TYPE")

    return walk(value, 1)


def sha(value):
    return "sha256:" + hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


class RawScanner:
    def __init__(self, raw: str):
        self.raw = raw
        self.index = 0
        self.nodes = 0
        self.total_string_bytes = 0

    def whitespace(self):
        while self.index < len(self.raw) and self.raw[self.index] in " \t\r\n":
            self.index += 1

    def string_token(self):
        self.whitespace()
        if self.index >= len(self.raw) or self.raw[self.index] != '"':
            fail("JSON_SYNTAX")
        start = self.index
        self.index += 1
        while self.index < len(self.raw):
            code = ord(self.raw[self.index])
            if self.raw[self.index] == "\\":
                self.index += 1
                if self.index >= len(self.raw):
                    fail("JSON_SYNTAX")
                if self.raw[self.index] == "u":
                    digits = self.raw[self.index + 1:self.index + 5]
                    if len(digits) != 4 or re.fullmatch(r"[0-9a-fA-F]{4}", digits) is None:
                        fail("JSON_SYNTAX")
                    self.index += 5
                else:
                    if self.raw[self.index] not in '"\\/bfnrt':
                        fail("JSON_SYNTAX")
                    self.index += 1
                continue
            if self.raw[self.index] == '"':
                self.index += 1
                try:
                    value = json.loads(self.raw[start:self.index])
                except (json.JSONDecodeError, ValueError):
                    fail("JSON_SYNTAX")
                state = {"totalStringBytes": self.total_string_bytes}
                validate_string(value, state)
                self.total_string_bytes = state["totalStringBytes"]
                return value
            if code < 0x20:
                fail("JSON_SYNTAX")
            self.index += 1
        fail("JSON_SYNTAX")

    def number_token(self):
        self.whitespace()
        match = re.match(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", self.raw[self.index:])
        if not match:
            fail("JSON_SYNTAX")
        token = match.group(0)
        self.index += len(token)
        if any(char in token for char in ".eE"):
            fail("FLOAT_NOT_ALLOWED")
        magnitude = token[1:] if token.startswith("-") else token
        if len(magnitude) > LIMITS["integerDigits"]:
            fail("LIMIT_INTEGER_DIGITS")
        if int(magnitude) > MAX_SAFE:
            fail("UNSAFE_INTEGER")

    def value(self, depth):
        if depth > LIMITS["depth"]:
            fail("LIMIT_DEPTH")
        self.nodes += 1
        if self.nodes > LIMITS["nodes"]:
            fail("LIMIT_NODES")
        self.whitespace()
        char = self.raw[self.index] if self.index < len(self.raw) else ""
        if char == "{":
            self.object(depth)
            return
        if char == "[":
            self.array(depth)
            return
        if char == '"':
            self.string_token()
            return
        if char == "-" or char.isdigit():
            self.number_token()
            return
        for literal in ("true", "false", "null"):
            if self.raw.startswith(literal, self.index):
                self.index += len(literal)
                return
        fail("JSON_SYNTAX")

    def object(self, depth):
        self.index += 1
        keys = set()
        self.whitespace()
        if self.index < len(self.raw) and self.raw[self.index] == "}":
            self.index += 1
            return
        while True:
            key = self.string_token()
            if key in keys:
                fail("DUPLICATE_JSON_KEY")
            keys.add(key)
            self.whitespace()
            if self.index >= len(self.raw) or self.raw[self.index] != ":":
                fail("JSON_SYNTAX")
            self.index += 1
            self.value(depth + 1)
            self.whitespace()
            if self.index < len(self.raw) and self.raw[self.index] == "}":
                self.index += 1
                return
            if self.index >= len(self.raw) or self.raw[self.index] != ",":
                fail("JSON_SYNTAX")
            self.index += 1

    def array(self, depth):
        self.index += 1
        self.whitespace()
        if self.index < len(self.raw) and self.raw[self.index] == "]":
            self.index += 1
            return
        while True:
            self.value(depth + 1)
            self.whitespace()
            if self.index < len(self.raw) and self.raw[self.index] == "]":
                self.index += 1
                return
            if self.index >= len(self.raw) or self.raw[self.index] != ",":
                fail("JSON_SYNTAX")
            self.index += 1

    def run(self):
        self.value(1)
        self.whitespace()
        if self.index != len(self.raw):
            fail("JSON_SYNTAX")


def parse_strict(raw: str):
    if not isinstance(raw, str):
        fail("JSON_SYNTAX")
    if len(raw.encode("utf-8", errors="surrogatepass")) > LIMITS["documentBytes"]:
        fail("LIMIT_DOCUMENT_BYTES")
    RawScanner(raw).run()

    def pairs_hook(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    def parse_int(token):
        return int(token)

    def no_float(_token):
        fail("FLOAT_NOT_ALLOWED")

    try:
        value = json.loads(raw, object_pairs_hook=pairs_hook, parse_int=parse_int,
                           parse_float=no_float, parse_constant=no_float)
    except ProfileError:
        raise
    except (json.JSONDecodeError, TypeError, ValueError):
        fail("JSON_SYNTAX")
    canonical(value)
    return value


def reject(reason):
    return {"verdict": "REJECT", "reason": reason}


def accept(reason="PROFILE_ACCEPT"):
    return {"verdict": "PASS", "reason": reason}


def exact_object(value, allowed, required=None):
    required = allowed if required is None else required
    if not isinstance(value, dict):
        return "SCHEMA_TYPE"
    if any(key not in allowed for key in value):
        return "SCHEMA_UNKNOWN_FIELD"
    if any(key not in value for key in required):
        return "SCHEMA_REQUIRED_FIELD_MISSING"
    return None


def nonempty(value):
    return isinstance(value, str) and len(value) > 0


def digest(value):
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def valid_rfc3339_ms(value):
    if not isinstance(value, str) or RFC3339_MS_RE.fullmatch(value) is None:
        return False
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        return False
    return parsed.year > 0 and parsed.microsecond % 1000 == 0


def extension_keys_nonempty(value):
    if isinstance(value, list):
        return all(extension_keys_nonempty(item) for item in value)
    if not isinstance(value, dict):
        return True
    return all(bool(key) and extension_keys_nonempty(child) for key, child in value.items())


def decimal(value):
    if not isinstance(value, str) or re.fullmatch(r"0|[1-9][0-9]*", value) is None or len(value) > LIMITS["decimalDigits"]:
        return None
    return int(value)


def sorted_string_set(value):
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        return False
    return len(set(value)) == len(value) and value == sorted(value, key=utf8_key)


def commitment_for_decision(decision):
    return sha(decision)


def validate_decision(decision):
    keys = ["schemaVersion", "canonicalization", "decisionId", "decidedAt", "authorityEvaluator", "policy",
            "principal", "server", "tool", "actionDigest", "declaration", "admission", "operations", "budgets",
            "listState", "anchor", "idempotencyContractDigest", "reasonCodes", "extensions"]
    error = exact_object(decision, keys)
    if error:
        return error
    if decision["schemaVersion"] != PROFILE or decision["canonicalization"] != C14N:
        return "DECISION_VERSION"
    if not nonempty(decision["decisionId"]) or not nonempty(decision["authorityEvaluator"]):
        return "DECISION_IDENTITY_TYPE"
    if not valid_rfc3339_ms(decision["decidedAt"]):
        return "INVALID_RFC3339_INSTANT"
    for key, fields in (("policy", ["id", "revision"]), ("principal", ["id"]), ("server", ["id"]), ("tool", ["id"])):
        error = exact_object(decision[key], fields)
        if error:
            return error
    identity_values = [decision["policy"]["id"], decision["policy"]["revision"], decision["principal"]["id"],
                       decision["server"]["id"], decision["tool"]["id"]]
    if not all(nonempty(value) for value in identity_values):
        return "DECISION_IDENTITY_TYPE"
    if not digest(decision["actionDigest"]):
        return "ACTION_DIGEST_TYPE"

    error = exact_object(decision["declaration"], ["digest", "authenticated"])
    if error:
        return error
    if not digest(decision["declaration"]["digest"]):
        return "DECLARATION_DIGEST_TYPE"
    if not isinstance(decision["declaration"]["authenticated"], bool):
        return "DECLARATION_AUTH_TYPE"
    if decision["declaration"]["authenticated"] is not True:
        return "DECLARATION_UNAUTHENTICATED"

    error = exact_object(decision["admission"], ["reference", "digest", "status"])
    if error:
        return error
    if not nonempty(decision["admission"]["reference"]) or not digest(decision["admission"]["digest"]):
        return "ADMISSION_TYPE"
    if decision["admission"]["status"] != "admitted":
        return "SERVER_NOT_ADMITTED"

    op_keys = ["requested", "hostAllowed", "effective", "denied", "reduced"]
    error = exact_object(decision["operations"], op_keys)
    if error:
        return error
    for key in op_keys:
        if not sorted_string_set(decision["operations"][key]):
            return key.upper() + "_SET_INVALID"
    requested = decision["operations"]["requested"]
    allowed_set = set(decision["operations"]["hostAllowed"])
    effective = [item for item in requested if item in allowed_set]
    denied = [item for item in requested if item not in allowed_set]
    effective_set = set(effective)
    reduced = [item for item in requested if item not in effective_set]
    if decision["operations"]["effective"] != effective:
        return "EFFECTIVE_NOT_EXACT_INTERSECTION"
    if decision["operations"]["denied"] != denied:
        return "DENIED_SET_MISMATCH"
    if decision["operations"]["reduced"] != reduced:
        return "REDUCED_SET_MISMATCH"

    budget_keys = ["unit", "requested", "hostAllowed", "effective", "denied", "reduced"]
    error = exact_object(decision["budgets"], budget_keys)
    if error:
        return error
    if not nonempty(decision["budgets"]["unit"]):
        return "BUDGET_TYPE"
    requested_budget = decimal(decision["budgets"]["requested"])
    allowed_budget = decimal(decision["budgets"]["hostAllowed"])
    effective_budget = decimal(decision["budgets"]["effective"])
    denied_budget = decimal(decision["budgets"]["denied"])
    reduced_budget = decimal(decision["budgets"]["reduced"])
    if any(value is None for value in (requested_budget, allowed_budget, effective_budget, denied_budget, reduced_budget)):
        return "BUDGET_TYPE"
    exact_effective = min(requested_budget, allowed_budget)
    if effective_budget != exact_effective:
        return "BUDGET_INCREASE" if effective_budget > exact_effective else "BUDGET_EFFECTIVE_NOT_EXACT_MIN"
    exact_denied = max(requested_budget - allowed_budget, 0)
    if denied_budget != exact_denied:
        return "BUDGET_DENIED_MISMATCH"
    if reduced_budget != requested_budget - effective_budget:
        return "BUDGET_REDUCED_MISMATCH"

    error = exact_object(decision["listState"], ["epoch", "digest", "materialChange", "regated"])
    if error:
        return error
    state = decision["listState"]
    if not nonempty(state["epoch"]) or not digest(state["digest"]) or not isinstance(state["materialChange"], bool) or not isinstance(state["regated"], bool):
        return "LIST_STATE_TYPE"
    if state["materialChange"] and not state["regated"]:
        return "MATERIAL_CHANGE_REQUIRES_REGATE"

    anchor_keys = ["id", "generation", "captureGeneration", "settlementGeneration", "state", "deactivatedAfterBinding"]
    error = exact_object(decision["anchor"], anchor_keys)
    if error:
        return error
    anchor = decision["anchor"]
    if not all(nonempty(anchor[key]) for key in ("id", "generation", "captureGeneration", "settlementGeneration")) or not isinstance(anchor["deactivatedAfterBinding"], bool):
        return "ANCHOR_TYPE"
    if anchor["state"] == "deactivated-before-binding":
        return "PREBINDING_INACTIVE"
    if anchor["state"] != "bound":
        return "BINDING_STATE"
    if anchor["captureGeneration"] != anchor["generation"]:
        return "FUTURE_CAPTURE_REJECTED"
    if anchor["settlementGeneration"] != anchor["generation"]:
        return "HISTORICAL_BINDING_MISMATCH"
    if not digest(decision["idempotencyContractDigest"]):
        return "IDEMPOTENCY_DIGEST_TYPE"
    if not sorted_string_set(decision["reasonCodes"]):
        return "REASON_CODES_INVALID"
    if not isinstance(decision["extensions"], dict):
        return "EXTENSIONS_TYPE"
    if not extension_keys_nonempty(decision["extensions"]):
        return "EXTENSION_KEY"
    reduction_exists = bool(decision["operations"]["denied"] or decision["operations"]["reduced"] \
                            or denied_budget > 0 or reduced_budget > 0)
    if reduction_exists and not decision["reasonCodes"]:
        return "REASON_CODES_REQUIRED"
    return None


def validate_decision_evidence(evidence, decision):
    if isinstance(evidence, dict) and "form" in evidence and evidence["form"] != "structured+digest":
        return "UNSUPPORTED_PUBLIC_FORM"
    error = exact_object(evidence, ["form", "algorithm", "canonicalization", "digest"])
    if error:
        return "DECISION_COMMITMENT_MISSING" if error == "SCHEMA_REQUIRED_FIELD_MISSING" else error
    if evidence["form"] != "structured+digest":
        return "UNSUPPORTED_PUBLIC_FORM"
    if evidence["algorithm"] != "sha-256":
        return "DECISION_ALGORITHM_UNSUPPORTED"
    if evidence["canonicalization"] != C14N or not digest(evidence["digest"]):
        return "DECISION_COMMITMENT_TYPE"
    if evidence["digest"] != commitment_for_decision(decision):
        return "DECISION_COMMITMENT_SUBSTITUTED"
    return None


def evaluate(record):
    try:
        canonical(record)
    except ProfileError as exc:
        return reject(str(exc))
    error = exact_object(record, ["decision", "decisionEvidence"])
    if error:
        return reject(error if isinstance(record, dict) else "RECORD_TYPE")
    error = validate_decision(record["decision"])
    if error:
        return reject(error)
    error = validate_decision_evidence(record["decisionEvidence"], record["decision"])
    if error:
        return reject(error)
    return accept("PASS_STRUCTURED_DECISION")


MUTATION_OPERATORS = [
    "unknown-top-level", "unknown-decision-field", "effective-escalation", "denied-set-mismatch",
    "reduced-set-mismatch", "budget-increase", "budget-denied-mismatch", "declaration-unauthenticated",
    "admission-denied", "future-capture", "material-list-not-regated", "reason-codes-unsorted",
    "evidence-digest-substitution", "algorithm-substitution", "idempotency-digest-invalid", "committed-extension-substitution",
]


def mutate_by_operator(record, operator_index, index):
    marker = f"mutation-{operator_index}-{index}"
    if operator_index == 0:
        record[f"unknown_{index}"] = marker
    elif operator_index == 1:
        record["decision"][f"unknown_{index}"] = marker
    else:
        record["decision"]["extensions"]["mutationMarker"] = marker
        if operator_index == 2:
            record["decision"]["operations"]["effective"].append(f"write:{index}")
            record["decision"]["operations"]["effective"].sort(key=utf8_key)
        elif operator_index == 3:
            record["decision"]["operations"]["denied"] = [f"denied:{index}"]
        elif operator_index == 4:
            record["decision"]["operations"]["reduced"] = [f"reduced:{index}"]
        elif operator_index == 5:
            record["decision"]["budgets"]["effective"] = str(1000 + index)
        elif operator_index == 6:
            record["decision"]["budgets"]["denied"] = str(index + 1)
        elif operator_index == 7:
            record["decision"]["declaration"]["authenticated"] = False
        elif operator_index == 8:
            record["decision"]["admission"]["status"] = "denied"
        elif operator_index == 9:
            record["decision"]["anchor"]["captureGeneration"] = str(1000 + index)
        elif operator_index == 10:
            record["decision"]["listState"].update({"epoch": f"epoch-{index}", "materialChange": True, "regated": False})
        elif operator_index == 11:
            record["decision"]["reasonCodes"] = [f"Z-{index}", f"A-{index}"]
        elif operator_index == 12:
            record["decisionEvidence"]["digest"] = f"sha256:{index:064x}"
        elif operator_index == 13:
            record["decisionEvidence"]["algorithm"] = f"sha-{index + 1}"
        elif operator_index == 14:
            record["decision"]["idempotencyContractDigest"] = f"invalid-{index}"


def mutation_suite(base, count=4096):
    if count != 4096:
        fail("MUTATION_COUNT_MUST_BE_4096")
    digests = []
    reasons = {}
    operators = {}
    unexpected = 0
    for index in range(count):
        operator_index = index // 256
        operator = MUTATION_OPERATORS[operator_index]
        instance = index % 256
        record = copy.deepcopy(base)
        mutate_by_operator(record, operator_index, instance)
        result = evaluate(record)
        if result["verdict"] != "REJECT":
            unexpected += 1
        reasons[result["reason"]] = reasons.get(result["reason"], 0) + 1
        operators[operator] = operators.get(operator, 0) + 1
        digests.append(sha({"operator": operator, "instance": instance, "record": record}))
    root = hashlib.sha256("\n".join(digests).encode("utf-8")).hexdigest()
    return {
        "count": count,
        "unique": len(set(digests)),
        "operatorCount": len(MUTATION_OPERATORS),
        "operators": operators,
        "corpusRoot": "sha256:" + root,
        "unexpectedAcceptance": unexpected,
        "reasonCounts": {key: reasons[key] for key in sorted(reasons, key=utf8_key)},
    }


def causal_controls(base):
    def effective(record):
        record["decision"]["operations"]["effective"].append("write")
        return lambda: record["decision"]["operations"]["effective"].pop()

    def policy(record):
        old = record["decision"]["policy"]["revision"]
        record["decision"]["policy"]["revision"] = "policy-other"
        return lambda: record["decision"]["policy"].__setitem__("revision", old)

    def anchor(record):
        old = record["decision"]["anchor"]["id"]
        record["decision"]["anchor"]["id"] = "anchor-other"
        return lambda: record["decision"]["anchor"].__setitem__("id", old)

    def extension(record):
        record["decision"]["extensions"]["transient"] = "changed"
        return lambda: record["decision"]["extensions"].pop("transient")

    def action(record):
        old = record["decision"]["actionDigest"]
        record["decision"]["actionDigest"] = "sha256:" + "f" * 64
        return lambda: record["decision"].__setitem__("actionDigest", old)

    controls = []
    for identifier, perturb in (("effective-escalation", effective), ("policy-revision-substitution", policy),
                                ("anchor-id-substitution", anchor), ("extension-substitution", extension),
                                ("action-digest-substitution", action)):
        record = copy.deepcopy(base)
        identity = id(record)
        before = canonical(record).encode("utf-8")
        before_digest = sha(record)
        green = evaluate(record)
        restore = perturb(record)
        red = evaluate(record)
        restore()
        after = canonical(record).encode("utf-8")
        after_digest = sha(record)
        restored = evaluate(record)
        passed = id(record) == identity and before == after and before_digest == after_digest \
            and green["verdict"] == "PASS" and red["verdict"] == "REJECT" and restored["verdict"] == "PASS"
        controls.append({
            "id": identifier, "sameObject": id(record) == identity, "green": green, "red": red, "restored": restored,
            "beforeDigest": before_digest, "afterDigest": after_digest, "byteEquality": before == after, "pass": passed,
        })
    return controls


def file_restoration_control(base, output_path):
    fixture_path = Path(str(output_path) + ".causal-restored.json")
    before = (canonical(base) + "\n").encode("utf-8")
    fixture_path.write_bytes(before)
    mutated = copy.deepcopy(base)
    mutated["decision"]["extensions"]["fileMutation"] = "same-path-red-control"
    fixture_path.write_bytes((canonical(mutated) + "\n").encode("utf-8"))
    red = evaluate(parse_strict(fixture_path.read_text(encoding="utf-8")))
    fixture_path.write_bytes(before)
    after = fixture_path.read_bytes()
    restored = evaluate(parse_strict(after.decode("utf-8")))
    before_hash = "sha256:" + hashlib.sha256(before).hexdigest()
    after_hash = "sha256:" + hashlib.sha256(after).hexdigest()
    return {
        "path": f"results/{fixture_path.name}", "samePath": True, "beforeSha256": before_hash, "afterSha256": after_hash,
        "byteEquality": before == after, "red": red, "restored": restored,
        "pass": before == after and red["verdict"] == "REJECT" and restored["verdict"] == "PASS",
    }


def known_answer_tests(kats):
    results = []
    for item in kats["cases"]:
        actual_canonical = None
        actual_digest = None
        error = None
        try:
            actual_canonical = canonical(item["value"])
            actual_digest = sha(item["value"])
        except ProfileError as exc:
            error = str(exc)
        actual_hex = actual_canonical.encode("utf-8").hex() if actual_canonical is not None else None
        results.append({
            "id": item["id"], "expectedCanonicalUtf8Hex": item["canonicalUtf8Hex"],
            "actualCanonicalUtf8Hex": actual_hex, "expectedDigest": item["digest"],
            "actualDigest": actual_digest, "error": error,
            "pass": error is None and actual_hex == item["canonicalUtf8Hex"] and actual_digest == item["digest"],
        })
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vectors", required=True)
    parser.add_argument("--parser", required=True)
    parser.add_argument("--kats", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    corpus = parse_strict(Path(args.vectors).read_text(encoding="utf-8"))
    kats = parse_strict(Path(args.kats).read_text(encoding="utf-8"))
    vector_results = []
    for vector in corpus["vectors"]:
        actual = evaluate(vector["record"])
        vector_results.append({
            "id": vector["id"], "kind": vector["kind"], "expected": vector["expected"], **actual,
            "expectationMatched": actual == vector["expected"],
        })
    parser_results = []
    for line in Path(args.parser).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        fixture = json.loads(line)
        try:
            parsed = parse_strict(fixture["raw"])
            actual = accept("PARSE_PASS") if fixture.get("operation") == "parse-only" else evaluate(parsed)
        except ProfileError as exc:
            actual = reject(str(exc))
        parser_results.append({
            "id": fixture["id"], "expected": fixture["expected"], **actual,
            "expectationMatched": actual == fixture["expected"],
        })
    base = next(vector["record"] for vector in corpus["vectors"] if vector["id"] == "BASE_STRUCTURED")
    report = {
        "schemaVersion": 3,
        "profile": PROFILE,
        "canonicalization": C14N,
        "implementation": "python-independent-v2_1",
        "runtimeFamily": "python",
        "limits": LIMITS,
        "vectorCount": len(vector_results),
        "kindCount": len({vector["kind"] for vector in corpus["vectors"]}),
        "vectors": vector_results,
        "parser": parser_results,
        "knownAnswerTests": known_answer_tests(kats),
        "mutations": mutation_suite(base),
        "causalControls": causal_controls(base),
    }
    report["fileRestorationControl"] = file_restoration_control(base, args.output)
    report["pass"] = (
        all(item["expectationMatched"] for item in vector_results)
        and all(item["expectationMatched"] for item in parser_results)
        and all(item["pass"] for item in report["knownAnswerTests"])
        and report["mutations"]["count"] == 4096
        and report["mutations"]["unique"] == 4096
        and report["mutations"]["operatorCount"] >= 16
        and report["mutations"]["unexpectedAcceptance"] == 0
        and all(item["pass"] for item in report["causalControls"])
        and report["fileRestorationControl"]["pass"]
    )
    Path(args.output).write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({
        "implementation": report["implementation"], "pass": report["pass"], "vectors": report["vectorCount"],
        "kinds": report["kindCount"], "parser": len(report["parser"]), "kats": len(report["knownAnswerTests"]),
        "mutations": report["mutations"]["count"], "operators": report["mutations"]["operatorCount"],
    }, separators=(",", ":")))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
