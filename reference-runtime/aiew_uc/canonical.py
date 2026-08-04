# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .errors import AUECError

MIN_I64 = -9_007_199_254_740_991
MAX_I64 = 9_007_199_254_740_991


def _reject_float(_: str) -> None:
    raise AUECError("E_FLOAT_FORBIDDEN", "floating-point numbers are forbidden")


def _reject_constant(value: str) -> None:
    raise AUECError("E_NONFINITE", f"non-finite number is forbidden: {value}")


def _parse_int(value: str) -> int:
    result = int(value, 10)
    if result < MIN_I64 or result > MAX_I64:
        raise AUECError("E_INTEGER_RANGE", "integer is outside the interoperable safe-integer range")
    return result


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AUECError("E_DUPLICATE_KEY", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _utf16_sort_key(value: str) -> bytes:
    try:
        return value.encode("utf-16-be", errors="strict")
    except UnicodeEncodeError as exc:
        raise AUECError("E_UNICODE", "unpaired Unicode surrogate is forbidden") from exc


def ensure_value(value: Any, *, max_depth: int = 64, max_items: int = 1_000_000) -> None:
    count = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal count
        count += 1
        if count > max_items:
            raise AUECError("E_ITEM_LIMIT", "JSON structure exceeds item bound")
        if depth > max_depth:
            raise AUECError("E_DEPTH", "JSON structure exceeds depth bound")
        if item is None or isinstance(item, bool):
            return
        if isinstance(item, int) and not isinstance(item, bool):
            if item < MIN_I64 or item > MAX_I64:
                raise AUECError("E_INTEGER_RANGE", "integer is outside the interoperable safe-integer range")
            return
        if isinstance(item, float):
            raise AUECError("E_FLOAT_FORBIDDEN", "floating-point numbers are forbidden")
        if isinstance(item, str):
            _utf16_sort_key(item)
            return
        if isinstance(item, Mapping):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise AUECError("E_OBJECT_KEY", "object keys must be strings")
                _utf16_sort_key(key)
                visit(child, depth + 1)
            return
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray, memoryview)):
            for child in item:
                visit(child, depth + 1)
            return
        raise AUECError("E_VALUE_TYPE", f"unsupported JSON value: {type(item).__name__}")

    visit(value, 0)


def strict_json_loads(data: str | bytes, *, max_bytes: int = 2_097_152) -> Any:
    raw = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    if len(raw) > max_bytes:
        raise AUECError("E_PAYLOAD_SIZE", "JSON payload exceeds byte bound")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(
            text,
            object_pairs_hook=_pairs_no_duplicates,
            parse_int=_parse_int,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except AUECError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise AUECError("E_JSON", "invalid JSON payload") from exc
    ensure_value(value)
    return value


def strict_json_load(path: str | Path, *, max_bytes: int = 2_097_152) -> Any:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise AUECError("E_IO", "cannot read JSON file") from exc
    return strict_json_loads(raw, max_bytes=max_bytes)


def _quote(value: str) -> str:
    _utf16_sort_key(value)
    out: list[str] = ['"']
    for ch in value:
        cp = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif cp < 0x20:
            out.append(f"\\u{cp:04x}")
        elif 0xD800 <= cp <= 0xDFFF:
            raise AUECError("E_UNICODE", "unpaired Unicode surrogate is forbidden")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _serialize(value: Any, *, depth: int = 0) -> str:
    if depth > 64:
        raise AUECError("E_DEPTH", "JSON structure exceeds depth bound")
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int) and not isinstance(value, bool):
        if value < MIN_I64 or value > MAX_I64:
            raise AUECError("E_INTEGER_RANGE", "integer is outside the interoperable safe-integer range")
        return str(value)
    if isinstance(value, float):
        raise AUECError("E_FLOAT_FORBIDDEN", "floating-point numbers are forbidden")
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, Mapping):
        parts: list[str] = []
        for key in sorted(value.keys(), key=_utf16_sort_key):
            if not isinstance(key, str):
                raise AUECError("E_OBJECT_KEY", "object keys must be strings")
            parts.append(_quote(key) + ":" + _serialize(value[key], depth=depth + 1))
        return "{" + ",".join(parts) + "}"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray, memoryview)):
        return "[" + ",".join(_serialize(item, depth=depth + 1) for item in value) + "]"
    raise AUECError("E_VALUE_TYPE", f"unsupported JSON value: {type(value).__name__}")


def canonical_json_text(value: Any) -> str:
    ensure_value(value)
    return _serialize(value)


def canonical_json_bytes(value: Any) -> bytes:
    return canonical_json_text(value).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def digest_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))
