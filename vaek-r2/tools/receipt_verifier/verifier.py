"""Independent VAEK R2 receipt-hash verifier for the fixed Solidity ABI layout."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from Crypto.Hash import keccak

HEX32 = re.compile(r"^0x[0-9a-fA-F]{64}$")
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
EFFECT = {"TRANSFER_ERC20": 0, "SWAP_EXACT_INPUT": 1, "BUY_SERVICE_ESCROW": 2}
RISK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


class ReceiptRejected(ValueError):
    pass


def _keccak(data: bytes) -> bytes:
    digest = keccak.new(digest_bits=256)
    digest.update(data)
    return digest.digest()


def _hex32(value: Any, field: str) -> bytes:
    if not isinstance(value, str) or not HEX32.fullmatch(value):
        raise ReceiptRejected(f"{field}: bytes32 required")
    return bytes.fromhex(value[2:])


def _uint(value: Any, bits: int, field: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]*", value):
        raise ReceiptRejected(f"{field}: canonical decimal string required")
    parsed = int(value)
    if parsed >= 2**bits:
        raise ReceiptRejected(f"{field}: overflow")
    return parsed.to_bytes(32, "big")


def _address(value: Any) -> bytes:
    if not isinstance(value, str) or not ADDRESS.fullmatch(value):
        raise ReceiptRejected("kernel/adapter: address required")
    return bytes(12) + bytes.fromhex(value[2:])


def recompute_receipt_hash(document: dict[str, Any]) -> str:
    required = {
        "chainId", "kernel", "executionId", "mandateId", "effectType", "requestedHash", "authorizedHash",
        "executedHash", "attenuationWitnessHash", "policyHash", "resourceRegistryVersion", "adapterAddress",
        "adapterVersion", "adapterCodeHash", "riskTier", "verificationSetHash", "requestedAt", "authorizedAt",
        "executedAt", "blockNumber", "actualInput", "actualOutput", "resultId", "receiptHash",
    }
    if set(document) != required:
        raise ReceiptRejected(f"unknown or missing fields: {sorted(set(document) ^ required)}")
    if document["effectType"] not in EFFECT or document["riskTier"] not in RISK:
        raise ReceiptRejected("unknown enum")

    words = [
        _keccak(b"VAEK/RECEIPT/R2"),
        _uint(document["chainId"], 256, "chainId"),
        _address(document["kernel"]),
        bytes(32),  # receipt.receiptHash is zero at the kernel's hash-computation step
        _hex32(document["executionId"], "executionId"),
        _hex32(document["mandateId"], "mandateId"),
        EFFECT[document["effectType"]].to_bytes(32, "big"),
        _hex32(document["requestedHash"], "requestedHash"),
        _hex32(document["authorizedHash"], "authorizedHash"),
        _hex32(document["executedHash"], "executedHash"),
        _hex32(document["attenuationWitnessHash"], "attenuationWitnessHash"),
        _hex32(document["policyHash"], "policyHash"),
        _uint(document["resourceRegistryVersion"], 64, "resourceRegistryVersion"),
        _address(document["adapterAddress"]),
        _uint(document["adapterVersion"], 64, "adapterVersion"),
        _hex32(document["adapterCodeHash"], "adapterCodeHash"),
        RISK[document["riskTier"]].to_bytes(32, "big"),
        _hex32(document["verificationSetHash"], "verificationSetHash"),
        _uint(document["requestedAt"], 64, "requestedAt"),
        _uint(document["authorizedAt"], 64, "authorizedAt"),
        _uint(document["executedAt"], 64, "executedAt"),
        _uint(document["blockNumber"], 64, "blockNumber"),
        _uint(document["actualInput"], 128, "actualInput"),
        _uint(document["actualOutput"], 128, "actualOutput"),
        _hex32(document["resultId"], "resultId"),
    ]
    return "0x" + _keccak(b"".join(words)).hex()


def verify_document(document: dict[str, Any]) -> bool:
    return recompute_receipt_hash(document).lower() == str(document.get("receiptHash", "")).lower()


def verify_path(path: Path) -> bool:
    return verify_document(json.loads(path.read_text(encoding="utf-8")))

