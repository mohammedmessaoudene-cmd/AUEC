# SPDX-License-Identifier: Apache-2.0
"""Deterministic mixed-license consistency audit."""

from __future__ import annotations

import csv
import argparse
import json
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
AGPL_HEADER = "# SPDX-License-Identifier: AGPL-3.0-only"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    errors: list[str] = []
    required = [
        "LICENSES/AGPL-3.0-only.txt",
        "LICENSES/Apache-2.0.txt",
        "LICENSES/CC-BY-4.0.txt",
        "LICENSING.md",
        "LICENSE_MAP.csv",
        "THIRD_PARTY_NOTICES.md",
    ]
    for rel in required:
        if not (root / rel).is_file():
            errors.append(f"missing {rel}")

    coupled = [
        path
        for path in (root / "reference-runtime").rglob("*.py")
        if "build" not in path.relative_to(root / "reference-runtime").parts
        and not any(part.endswith(".egg-info") for part in path.parts)
    ]
    coupled += list((root / "tests").rglob("*.py"))
    coupled.append(root / "examples" / "run_example.py")
    for path in sorted(coupled):
        first = path.read_text(encoding="utf-8").splitlines()[:2]
        if AGPL_HEADER not in first:
            errors.append(f"missing AGPL SPDX header: {path.relative_to(root)}")

    pyproject = (root / "reference-runtime" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    if 'license = "AGPL-3.0-only"' not in pyproject:
        errors.append("runtime pyproject license is not AGPL-3.0-only")
    runtime_license = (root / "reference-runtime" / "LICENSE").read_text(
        encoding="utf-8"
    )
    if "GNU AFFERO GENERAL PUBLIC LICENSE" not in runtime_license:
        errors.append("runtime LICENSE is not the AGPL text")

    zenodo = json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))
    if zenodo.get("license") != "other-open":
        errors.append(".zenodo.json record-level license must be other-open")
    zenodo_description = zenodo.get("description", "")
    for marker in (
        "CC BY 4.0",
        "Apache-2.0",
        "AGPL-3.0-only",
        "LICENSING.md",
        "LICENSE_MAP.csv",
    ):
        if marker not in zenodo_description:
            errors.append(f".zenodo.json mixed-license explanation missing: {marker}")
    citation = (root / "CITATION.cff").read_text(encoding="utf-8")
    if any(line.startswith("license:") for line in citation.splitlines()):
        errors.append(
            "CITATION.cff incorrectly collapses mixed licensing to one license"
        )

    for base in ("schemas", "tck", "sdk", "bindings"):
        for path in (root / base).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "aiew_gateway" in text or "aiew_uc" in text:
                errors.append(
                    f"Apache boundary imports AGPL runtime: {path.relative_to(root)}"
                )

    rights_path = root / "RIGHTS_AND_RELICENSING_REGISTER.csv"
    rows: list[dict[str, str]] = []
    if rights_path.is_file():
        with rights_path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        registered = {row["path"] for row in rows}
        for path in (root / "reference-runtime").rglob("*.py"):
            if "build" in path.relative_to(root / "reference-runtime").parts:
                continue
            if any(part.endswith(".egg-info") for part in path.parts):
                continue
            rel = path.relative_to(root).as_posix()
            if rel not in registered:
                errors.append(f"runtime source missing from rights register: {rel}")
        if any(row["right_to_commercial"].upper() == "YES" for row in rows):
            errors.append("commercial rights claimed despite unresolved title chain")

    if errors:
        print("LICENSE AUDIT FAIL")
        print("\n".join(f"- {item}" for item in errors))
        return 1
    if rows:
        print(
            f"LICENSE AUDIT PASS: {len(coupled)} AGPL-coupled Python files, {len(rows)} rights rows"
        )
    else:
        print(
            f"LICENSE AUDIT PASS (public mode): {len(coupled)} AGPL-coupled Python files; "
            "private rights-chain register intentionally absent"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
