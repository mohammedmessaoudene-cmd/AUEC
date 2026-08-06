# SPDX-License-Identifier: Apache-2.0
"""Fail-closed checks for the report's bounded scientific release contract."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "technical-report"


def main() -> int:
    errors: list[str] = []
    background = (REPORT / "sections" / "02_background.tex").read_text(encoding="utf-8")
    design = (REPORT / "sections" / "04_design.tex").read_text(encoding="utf-8")
    metadata = (REPORT / "metadata_public.tex").read_text(encoding="utf-8")
    all_tex = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(REPORT.rglob("*.tex"))
    )

    for citation in (
        "Basu2026",
        "YeTan2026",
        "MishraSharad2026",
        "Zhou2026",
        "Figuera2026",
    ):
        if not re.search(
            r"\\cite\{[^}]*\b" + re.escape(citation) + r"\b[^}]*\}", background
        ):
            errors.append(
                f"required contemporary citation absent from related work: {citation}"
            )

    required_design_fragments = (
        r"\kappa(x)",
        r"\rho(x)",
        r"\ell(x)",
        r"\operatorname{validated}_U(x,a)",
        r"\operatorname{consent}_U(a)",
        r"\varepsilon_i",
        r"r_0=0^{256}",
        r"\operatorname{lub}",
    )
    for fragment in required_design_fragments:
        if fragment not in design:
            errors.append(f"required mathematical fragment absent: {fragment}")

    if r"op_i,\kappa_i" in design or r"effect $\kappa_i$" in design:
        errors.append("epistemic/effect symbol collision")

    special_notice_command = "\\" + "IEEEspecialpapernotice"
    if special_notice_command in metadata:
        errors.append("special paper notice must be absent")
    if re.search(
        r"\b(?:accepted|published|endorsed|approved)\s+(?:by|in)\s+IEEE\b",
        metadata,
        flags=re.IGNORECASE,
    ):
        errors.append("forbidden IEEE publication-status claim")

    forbidden_claims = (
        r"\b(?:has|achieved|demonstrates|establishes|claims) official A2A conformance\b",
        r"\bA2A[- ]certified\b",
        r"\bproduction[- ]secure\b",
        r"\bjournal[- ]ready\b",
        r"\bstandard adopted\b",
    )
    for pattern in forbidden_claims:
        if re.search(pattern, all_tex, flags=re.IGNORECASE):
            errors.append(f"unsupported report claim: {pattern}")

    if errors:
        print("SCIENTIFIC RELEASE GATE FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("SCIENTIFIC RELEASE GATE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
