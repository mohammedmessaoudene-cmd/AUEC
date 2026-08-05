# SPDX-License-Identifier: AGPL-3.0-only
"""Corresponding-source metadata for the network-facing reference runtime."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import urlparse

RUNTIME_VERSION = "0.36.0a1"
RELEASE_TAG = "v0.36.0-prestandard"


def source_offer_payload(
    *,
    source_url: str | None = None,
    source_ref: str | None = None,
    source_sha256: str | None = None,
    modified: bool | None = None,
    modification_notice: str | None = None,
) -> dict[str, Any]:
    """Return bounded source-offer metadata and reject hidden modifications."""

    url = source_url if source_url is not None else os.environ.get("AUEC_SOURCE_RELEASE_URL", "")
    ref = source_ref or os.environ.get("AUEC_SOURCE_REF", RELEASE_TAG)
    digest = source_sha256 if source_sha256 is not None else os.environ.get("AUEC_SOURCE_ARCHIVE_SHA256", "")
    is_modified = modified if modified is not None else os.environ.get("AUEC_BUILD_MODIFIED", "0") == "1"
    notice = modification_notice
    if notice is None:
        notice = os.environ.get("AUEC_MODIFICATION_NOTICE", "").strip()
    if is_modified and not notice:
        raise RuntimeError("modified builds must disclose their modifications")

    parsed = urlparse(url)
    exact = (
        parsed.scheme == "https"
        and bool(parsed.netloc)
        and parsed.username is None
        and parsed.password is None
        and not parsed.fragment
        and bool(re.fullmatch(r"[0-9a-f]{64}", digest))
        and bool(ref)
        and all(0x20 <= ord(ch) <= 0x7E for ch in ref)
    )
    return {
        "license": "AGPL-3.0-only",
        "runtimeVersion": RUNTIME_VERSION,
        "sourceReleaseUrl": url or None,
        "sourceRef": ref,
        "sourceArchiveSha256": digest,
        "modified": is_modified,
        "modificationNotice": notice or None,
        "exactCorrespondingSource": exact,
        "status": "ready" if exact else "prepublication-unassigned",
        "disclaimer": "Engineering aid; deployment-specific license compliance requires human review.",
    }


def require_exact_source_offer(**kwargs: Any) -> dict[str, Any]:
    """Fail before non-loopback deployment unless source coordinates are exact."""

    payload = source_offer_payload(**kwargs)
    if not payload["exactCorrespondingSource"]:
        raise RuntimeError(
            "exact corresponding-source URL, release ref, and SHA-256 are required "
            "before non-loopback or publication deployment"
        )
    return payload
