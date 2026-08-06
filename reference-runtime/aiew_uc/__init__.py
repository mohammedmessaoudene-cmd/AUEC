# SPDX-License-Identifier: AGPL-3.0-only
"""AIEW Universal Execution Contract reference implementation."""

from .canonical import (
    canonical_json_bytes,
    canonical_json_text,
    digest_json,
    strict_json_loads,
)
from .authority import AuthorityDecision, evaluate_authority
from .runtime import UniversalRuntime, default_host_policy
from .store import ExecutionStore

__all__ = [
    "UniversalRuntime",
    "AuthorityDecision",
    "ExecutionStore",
    "canonical_json_bytes",
    "canonical_json_text",
    "default_host_policy",
    "digest_json",
    "evaluate_authority",
    "strict_json_loads",
]

__version__ = "0.36.0a1"
