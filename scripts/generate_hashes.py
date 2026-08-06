# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "HASHES.sha256"
TRANSIENT_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "venv",
}


def generate_manifest(root: Path, output: Path) -> int:
    root = root.resolve()
    output = output.resolve()
    excluded = {output, (root / MANIFEST_NAME).resolve()}
    excluded_rel = {
        "docs/technical-report/AUEC_Technical_Report_v0.35.0-prestandard.pdf",
        "docs/technical-report/AUEC_Technical_Report_v0.35.0-prestandard.pdf.sha256",
        "docs/technical-report/main_public.aux",
        "docs/technical-report/main_public.bbl",
        "docs/technical-report/main_public.blg",
        "docs/technical-report/main_public.log",
        "docs/technical-report/main_public.out",
        "docs/technical-report/main_public.pdf",
    }
    lines: list[str] = []
    files = (path for path in root.rglob("*") if path.is_file())
    for path in sorted(
        files, key=lambda candidate: candidate.relative_to(root).as_posix()
    ):
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(root).parts
        if (
            path.resolve() in excluded
            or rel in excluded_rel
            or any(part in TRANSIENT_PARTS for part in parts)
            or rel.startswith("tmp/")
            or rel.startswith("paper/build-")
            or rel.startswith("paper/repro-snapshot-")
            or rel.startswith("reference-runtime/build/")
            or any(part.endswith(".egg-info") for part in parts)
            or rel.endswith(".pyc")
            or rel == "MANIFEST.sha256"
        ):
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {rel}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return len(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = (args.output or root / MANIFEST_NAME).resolve()
    records = generate_manifest(root, output)
    print(f"WROTE {output}: {records} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
