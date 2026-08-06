# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "root", nargs="?", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output or root / "HASHES.sha256"
    excluded = {output.resolve()}
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
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(root).parts
        if (
            path.resolve() in excluded
            or rel in excluded_rel
            or "__pycache__" in parts
            or ".git" in parts
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
    print(f"WROTE {output}: {len(lines)} records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
