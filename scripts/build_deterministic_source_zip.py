# SPDX-License-Identifier: Apache-2.0
"""Build the public source archive with stable ordering and metadata."""

from __future__ import annotations

import argparse
import stat
import zipfile
from pathlib import Path


ZIP_TIMESTAMP = (2026, 8, 3, 1, 0, 0)
EXCLUDED_RELATIVE_PATHS = {
    "docs/technical-report/AUEC_Technical_Report_v0.35.0-prestandard.pdf",
    "docs/technical-report/AUEC_Technical_Report_v0.35.0-prestandard.pdf.sha256",
    "docs/technical-report/main_public.aux",
    "docs/technical-report/main_public.bbl",
    "docs/technical-report/main_public.blg",
    "docs/technical-report/main_public.log",
    "docs/technical-report/main_public.out",
    "docs/technical-report/main_public.pdf",
}
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "build",
    "dist",
}


def source_files(root: Path, output: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        rel = relative.as_posix()
        if path.resolve() == output.resolve():
            continue
        if any(part in EXCLUDED_DIRECTORY_NAMES or part.endswith(".egg-info") for part in relative.parts):
            continue
        if rel in EXCLUDED_RELATIVE_PATHS or rel.endswith((".pyc", ".pyo")):
            continue
        if path.is_symlink():
            raise RuntimeError(f"symbolic links are not allowed in the source archive: {rel}")
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--prefix", default="AUEC_v0.36.0_PRESTANDARD")
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    files = source_files(root, output)
    with zipfile.ZipFile(
        output,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for path in files:
            rel = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(f"{args.prefix}/{rel}", date_time=ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.flag_bits |= 0x800
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    print(f"WROTE {output}: {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
