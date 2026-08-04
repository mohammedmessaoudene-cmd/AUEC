# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .canonical import canonical_json_text, digest_json, strict_json_loads
from .errors import AUECError
from .runtime import UniversalRuntime


class ExecutionStore:
    """Crash-consistent idempotence store for complete U0 results.

    SQLite atomic commit protects the result record. Logical receipts remain
    deterministic; operational durability is a host property, not semantic truth.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS executions ("
                "manifest_id TEXT PRIMARY KEY, manifest_digest TEXT NOT NULL, result_json TEXT NOT NULL, result_digest TEXT)"
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(executions)")}
            if "result_digest" not in columns:
                conn.execute("ALTER TABLE executions ADD COLUMN result_digest TEXT")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a configured connection and always close it.

        ``sqlite3.Connection`` as a context manager controls transactions but
        does not guarantee that the connection object is closed.  This wrapper
        makes connection lifetime explicit and lets SQLite roll back an open
        transaction when an injected crash leaves the block exceptionally.
        """
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        try:
            conn.execute("PRAGMA busy_timeout=30000")
            yield conn
        finally:
            conn.close()

    def execute_once(self, runtime: UniversalRuntime, manifest: dict[str, Any], fault_hook: Any | None = None) -> dict[str, Any]:
        manifest_id = manifest.get("manifestId")
        if not isinstance(manifest_id, str):
            return runtime.execute(manifest)
        digest = digest_json(manifest)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            if fault_hook is not None:
                fault_hook("after_begin")
            row = conn.execute(
                "SELECT manifest_digest, result_json FROM executions WHERE manifest_id = ?", (manifest_id,)
            ).fetchone()
            if row is not None:
                if row[0] != digest:
                    conn.execute("ROLLBACK")
                    raise AUECError("E_NONCE_COLLISION", "manifestId was reused with different content")
                result = strict_json_loads(row[1])
                conn.execute("COMMIT")
                return result
            result = runtime.execute(manifest)
            if fault_hook is not None:
                fault_hook("after_execute")
            conn.execute(
                "INSERT INTO executions(manifest_id, manifest_digest, result_json, result_digest) VALUES (?, ?, ?, ?)",
                (manifest_id, digest, canonical_json_text(result), digest_json(result)),
            )
            if fault_hook is not None:
                fault_hook("after_insert")
            conn.execute("COMMIT")
            if fault_hook is not None:
                fault_hook("after_commit")
            return result

    def verify(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT manifest_digest, result_json, result_digest FROM executions ORDER BY manifest_id").fetchall()
        for manifest_digest, result_json, result_digest in rows:
            if not isinstance(manifest_digest, str) or not manifest_digest.startswith("sha256:"):
                raise AUECError("E_STORE", "invalid manifest digest in store")
            result = strict_json_loads(result_json)
            if not isinstance(result, dict) or result.get("auecVersion") != "0.1":
                raise AUECError("E_STORE", "invalid stored result")
            if result_digest != digest_json(result):
                raise AUECError("E_STORE_TAMPER", "stored result digest mismatch")
        return {"executions": len(rows)}
