# SPDX-License-Identifier: AGPL-3.0-only
"""AIEW Universal Execution Contract reference implementation."""

from .canonical import canonical_json_bytes, canonical_json_text, digest_json, strict_json_loads
from .runtime import UniversalRuntime, default_host_policy
from .store import ExecutionStore

__all__ = [
    "UniversalRuntime",
    "ExecutionStore",
    "canonical_json_bytes",
    "canonical_json_text",
    "default_host_policy",
    "digest_json",
    "strict_json_loads",
]

__version__ = "0.5.0a1"
