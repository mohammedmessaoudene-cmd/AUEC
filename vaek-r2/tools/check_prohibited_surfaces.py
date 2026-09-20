"""Fail CI if the VAEK execution path regains an agent-controlled generic call surface."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAN = [ROOT / "src", ROOT / "agent"]
FORBIDDEN = {
    "delegatecall/callcode": re.compile(r"\.(?:delegatecall|callcode)\s*\("),
    "generic executable bytes": re.compile(r"\bbytes\s+(?:calldata|memory)\s+(?:data|payload|calldata_)\b"),
    "generic execute target bytes": re.compile(r"function\s+execute\w*\s*\([^)]*address\s+\w+[^)]]*bytes\b", re.S),
    "assembly": re.compile(r"\bassembly\s*\{"),
}


def main() -> int:
    failures: list[str] = []
    for base in SCAN:
        for path in sorted(base.rglob("*")):
            if path.suffix not in {".sol", ".py"}:
                continue
            text = path.read_text(encoding="utf-8")
            for label, pattern in FORBIDDEN.items():
                if pattern.search(text):
                    failures.append(f"{path.relative_to(ROOT)}: {label}")
            reviewed_low_level = path.name == "TokenOps.sol" or "mocks" in path.parts
            if path.suffix == ".sol" and not reviewed_low_level and re.search(r"\.(?:call|staticcall)\s*\(", text):
                failures.append(f"{path.relative_to(ROOT)}: low-level call outside reviewed TokenOps")
    if failures:
        print("PROHIBITED_SURFACE_SCAN=FAIL")
        print("\n".join(failures))
        return 1
    print("PROHIBITED_SURFACE_SCAN=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
