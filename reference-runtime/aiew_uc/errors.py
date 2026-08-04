# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    message: str


class AUECError(Exception):
    """Bounded, protocol-safe error carrying a stable machine code."""

    def __init__(self, code: str, message: str) -> None:
        self.info = ErrorInfo(code=code, message=message[:256])
        super().__init__(self.info.message)
