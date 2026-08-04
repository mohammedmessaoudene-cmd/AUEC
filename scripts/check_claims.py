# SPDX-License-Identifier: Apache-2.0
"""Reject a small set of dangerous publication overclaims."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {
    ".git",
    "__pycache__",
    "prompts",
    "evidence",
    "LICENSES",
    "release",
    "build",
    "artifacts",
    "logs",
    "tmp",
    "dist-prestandard",
}
TEXT_SUFFIXES = {".md", ".txt", ".json", ".cff", ".toml", ".tex", ".csv", ".yml", ".yaml", ".py"}
FORBIDDEN = {
    r"\bOpenAI is (?:an? )?(?:official )?partner\b": "false OpenAI affiliation",
    r"\bOpenAI (?:co-invented|owns) AIEW\b": "false OpenAI ownership or inventorship",
    r"\bZenodo proves worldwide inventorship\b": "false legal effect of DOI",
    r"\bAGPL covers all cloud infrastructure\b": "false AGPL scope",
    r"\bAUEC is an official (?:MCP|A2A|W3C|IETF) standard\b": "false standard adoption",
    r"\b(?:has|achieved|demonstrates|establishes|claims) official A2A conformance\b": "unsupported official A2A conformance claim",
    r"\bA2A[- ]certified\b": "unsupported A2A certification claim",
    r"\bproduction security (?:is )?certified\b": "false production certification",
}


def files_for(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_file():
            found.append(path)
            continue
        for candidate in path.rglob("*"):
            if candidate.is_file() and candidate.suffix.lower() in TEXT_SUFFIXES:
                if not any(part in SKIP_PARTS for part in candidate.parts):
                    found.append(candidate)
    return sorted(set(found))


def scan(paths: list[Path]) -> list[str]:
    findings: list[str] = []
    for path in files_for(paths):
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern, reason in FORBIDDEN.items():
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path}:{line}: {reason}: {match.group(0)!r}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    paths = args.paths or [ROOT]
    findings = scan(paths)
    if findings:
        print("CLAIMS AUDIT FAIL")
        print("\n".join(findings))
        return 1
    print("CLAIMS AUDIT PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
