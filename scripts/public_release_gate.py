# SPDX-License-Identifier: Apache-2.0
"""Fail-closed checks for the public AUEC release candidate."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
TEXT_SUFFIXES = {".md", ".txt", ".json", ".csv", ".cff", ".py", ".toml", ".tex", ".bib", ".yml", ".yaml"}
FORBIDDEN_NAME_PARTS = {"human-signoff", "reviews", "prompts", "outreach", "journal"}
FORBIDDEN_PUBLIC_MARKERS = (
    r"(?i)\bR\d{1,3}\b",
    r"(?i)AIEW_R",
    r"(?i)REPOSITORY_URL_PENDING",
    r"(?i)PENDING_FINAL_APPROVAL",
    r"(?i)preparation campaign",
    r"(?i)This placeholder must be replaced",
    r"(?i)\b(?:[A-Z]:\\Users\\|D:\\iascript|/mnt/data|/home/|/Users/)",
)


def main() -> int:
    errors: list[str] = []
    for path in ROOT.rglob("*"):
        if "__pycache__" in path.parts or path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if any(part in rel.lower() for part in FORBIDDEN_NAME_PARTS):
            errors.append(f"private or journal asset present: {rel}")
        if re.search(r"(?i)(?:^|[/_.-])R\d{1,3}(?:[/_.-]|$)|AIEW_R", rel):
            errors.append(f"internal label in public path: {rel}")
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.resolve() == SELF:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in FORBIDDEN_PUBLIC_MARKERS:
            if re.search(pattern, text):
                errors.append(f"forbidden public marker {pattern}: {rel}")
        if re.search(r"(?i)(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|BEGIN (?:RSA |OPENSSH )?PRIVATE KEY)", text):
            errors.append(f"credential pattern: {rel}")
        if re.search(r"(?i)\b(disability|disabled person|medical diagnosis|health condition)\b", text):
            errors.append(f"health disclosure: {rel}")

    required = {
        "README.md",
        "CITATION.cff",
        ".zenodo.json",
        "codemeta.json",
        "LICENSE",
        "LICENSING.md",
        "LICENSE_MAP.csv",
        "CLA_REVIEW_REQUIRED.md",
        "THIRD_PARTY_NOTICES.md",
        "SECURITY.md",
        "PUBLICATION_RECORD.md",
        "PUBLIC_RIGHTS_PROVENANCE_MAP.csv",
        "scripts/scientific_release_gate.py",
        "docs/technical-report/AUEC_Technical_Report_v0.35.0-prestandard.pdf",
    }
    for rel in sorted(required):
        if not (ROOT / rel).is_file():
            errors.append(f"missing required file: {rel}")

    zenodo = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    if zenodo.get("upload_type") != "software":
        errors.append("Zenodo upload_type is not software")
    if zenodo.get("version") != "0.35.0-prestandard":
        errors.append("Zenodo version mismatch")
    if zenodo.get("license") != "other-open":
        errors.append("Zenodo record-level license must be other-open")
    zenodo_description = zenodo.get("description", "")
    for marker in ("CC BY 4.0", "Apache-2.0", "AGPL-3.0-only", "LICENSING.md", "LICENSE_MAP.csv"):
        if marker not in zenodo_description:
            errors.append(f"Zenodo mixed-license explanation missing: {marker}")
    if "does not replace the governing per-path licenses" not in zenodo_description:
        errors.append("Zenodo record-level license disclaimer is missing")

    citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    if 'version: "0.35.0-prestandard"' not in citation:
        errors.append("CITATION version mismatch")
    if 'repository-code: "https://github.com/mohammedmessaoudene-cmd/AUEC"' not in citation:
        errors.append("CITATION repository coordinate mismatch")
    if 'date-released: "2026-08-04"' not in citation:
        errors.append("CITATION release date mismatch")
    if 'doi: "10.5281/zenodo.21796636"' not in citation:
        errors.append("CITATION DOI mismatch")

    with (ROOT / "LICENSE_MAP.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    mapping = {row["path_pattern"]: row["spdx_expression"] for row in rows}
    expected = {
        "reference-runtime/**": "AGPL-3.0-only",
        "tests/**": "AGPL-3.0-only",
        "schemas/**": "Apache-2.0",
        "tck/**": "Apache-2.0",
        "sdk/**": "Apache-2.0",
        "bindings/**": "Apache-2.0",
        "docs/**": "CC-BY-4.0",
    }
    for pattern, license_id in expected.items():
        if mapping.get(pattern) != license_id:
            errors.append(f"license routing mismatch: {pattern}")

    record = (ROOT / "PUBLICATION_RECORD.md").read_text(encoding="utf-8")
    for invariant in (
        "repositoryUrl = https://github.com/mohammedmessaoudene-cmd/AUEC",
        "doi = 10.5281/zenodo.21796636",
        "publicationDate = 2026-08-04",
        "githubPublicationPerformed = true",
        "zenodoPublicationPerformed = false",
        "doiReserved = true",
        "journalSubmissionPerformed = false",
        "standardsSubmissionPerformed = false",
        "externalContactPerformed = false",
    ):
        if invariant not in record:
            errors.append(f"publication invariant missing: {invariant}")

    metadata = (ROOT / "docs/technical-report/metadata_public.tex").read_text(encoding="utf-8")
    if "Maître de conférences B (MCB)" not in metadata:
        errors.append("author academic appointment is missing")
    if "Belhadj Bouchaib University of Ain Temouchent" not in metadata:
        errors.append("author university affiliation is missing")
    former_department = "Department of " + "Electronics and Telecommunications"
    if former_department in metadata:
        errors.append("department-level affiliation must be absent")
    if "is with the" in metadata:
        errors.append("collaboration-like affiliation wording must be absent")
    if "does not imply sponsorship, collaboration, or endorsement by the university" not in metadata:
        errors.append("employment-only affiliation clarification is missing")
    special_notice_command = "\\" + "IEEEspecialpapernotice"
    if special_notice_command in metadata:
        errors.append("report special paper notice must be absent")
    if re.search(
        r"\b(?:accepted|published|endorsed|approved)\s+(?:by|in)\s+IEEE\b",
        metadata,
        flags=re.IGNORECASE,
    ):
        errors.append("forbidden IEEE publication-status claim")

    if errors:
        print("PUBLIC RELEASE GATE FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"PUBLIC RELEASE GATE PASS: {sum(1 for p in ROOT.rglob('*') if p.is_file())} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
