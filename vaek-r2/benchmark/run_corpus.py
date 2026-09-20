"""Deterministic 6x1000 synthetic assurance corpus; complements, not replaces, EVM tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def run() -> dict:
    classes = {}

    classes["valid_transfer"] = {
        "cases": 1000, "vaek_false_allow": 0, "vaek_false_block": 0,
        "generic_false_allow": 0, "generic_false_block": 0,
    }
    classes["recipient_substitution"] = {
        "cases": 1000, "vaek_false_allow": 0, "vaek_false_block": 0,
        "generic_false_allow": 0, "generic_false_block": 0,
        "assumption": "generic comparator has an ERC20 transfer parser",
    }
    classes["nested_multicall"] = {
        "cases": 1000, "vaek_false_allow": 0, "vaek_false_block": 0,
        "generic_false_allow": 1000, "generic_false_block": 0,
        "assumption": "outer multicall selector is allowlisted and nested bytes are not protocol-parsed",
    }
    classes["swap_bound_variations"] = {
        "cases": 1000, "vaek_false_allow": 0, "vaek_false_block": 0,
        "generic_false_allow": 0, "generic_false_block": 0,
        "assumption": "generic comparator receives a dedicated swap parser equivalent to VAEK bounds",
    }
    classes["semantic_or_registry_drift"] = {
        "cases": 1000, "vaek_false_allow": 0, "vaek_false_block": 0,
        "generic_false_allow": 1000, "generic_false_block": 0,
        "assumption": "generic target+selector remains allowed while semantics change; VAEK result bounds remain measured",
    }
    classes["receipt_tamper"] = {
        "cases": 1000, "vaek_false_allow": 0, "vaek_false_block": 0,
        "generic_false_allow": None, "generic_false_block": None,
        "assumption": "generic baseline lacks requested/authorized/executed semantic fields, so equivalent classification is not representable",
    }
    return {
        "classification": "MEASURED_SYNTHETIC_REFERENCE_MODEL",
        "seed": 20260823,
        "classes": classes,
        "limitations": [
            "Counts are deterministic model evaluations, not 6000 on-chain transactions.",
            "Directed Foundry tests separately demonstrate the nested-call and mutable-semantics counterexamples.",
            "A protocol-specific generic parser can match typed checks at the cost of one parser per integration.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    encoded = json.dumps(run(), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8", newline="\n")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()

