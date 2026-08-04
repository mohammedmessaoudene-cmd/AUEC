# SPDX-License-Identifier: AGPL-3.0-only
"""AUEC transport gateway reference implementation.

This package exposes the transport-neutral AUEC U0 runtime through concrete
MCP 2025-11-25, A2A 1.0 JSON-RPC, HTTP+JSON, and browser-adapter surfaces.
It is an engineering alpha, not a production security boundary.
"""

__version__ = "0.35.0a1"

from .core import GatewayState
from .server import GatewayHTTPServer, create_server

__all__ = ["GatewayState", "GatewayHTTPServer", "create_server", "__version__"]
