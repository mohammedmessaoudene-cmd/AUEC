#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a byte-deterministic narrowed Reviewer V2.1 Core ZIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path

FIXED_TIMESTAMP = (2026, 8, 23, 0, 0, 0)
GENERATED = {"PACKAGE_CONTENTS.json", "PACKAGE_MANIFEST.sha256"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def selected_files(root: Path):
    result = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        parts = relative.split("/")
        if "__pycache__" in parts or relative.endswith(".pyc"):
            continue
        if parts[0] == "meeting":
            continue
        if relative in GENERATED:
            continue
        result.append((relative, path))
    return sorted(result, key=lambda item: item[0].encode("utf-8"))


def write_generated(root: Path):
    payload = selected_files(root)
    contents = {
        "schemaVersion": 1,
        "artifact": "MCP_AUTHORITY_DELTA_REVIEWER_V2_1_CORE_20260823",
        "deterministicBuild": True,
        "fixedZipTimestamp": "2026-08-23T00:00:00Z",
        "files": [
            {"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path.read_bytes())}
            for relative, path in payload
        ],
    }
    contents_bytes = (json.dumps(contents, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    (root / "PACKAGE_CONTENTS.json").write_bytes(contents_bytes)
    with_contents = selected_files(root) + [("PACKAGE_CONTENTS.json", root / "PACKAGE_CONTENTS.json")]
    with_contents.sort(key=lambda item: item[0].encode("utf-8"))
    manifest = "".join(f"{sha256(path.read_bytes())}  {relative}\n" for relative, path in with_contents)
    (root / "PACKAGE_MANIFEST.sha256").write_bytes(manifest.encode("utf-8"))


def build(root: Path, output: Path):
    write_generated(root)
    files = selected_files(root)
    files.extend((name, root / name) for name in sorted(GENERATED, key=lambda value: value.encode("utf-8")))
    files.sort(key=lambda item: item[0].encode("utf-8"))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for relative, path in files:
            info = zipfile.ZipInfo(relative, FIXED_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    data = output.read_bytes()
    return {"path": str(output), "bytes": len(data), "sha256": sha256(data), "files": len(files)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = build(Path(args.root).resolve(), Path(args.output).resolve())
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
