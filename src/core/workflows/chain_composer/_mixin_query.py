"""
chain_composer._mixin_query — Query and database mixin for ChainComposer.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from typing import Any

from src.core.workflows.chain_composer._types import (
    ChainStep,
    ChainStepType,
    ChainStatus,
    ComposedChain,
    ChainStepResult,
    ChainExecutionResult,
)

_DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")
_DB_PATH = os.path.join(_DB_DIR, "chain_composer.sqlite")


class QueryMixin:
    """Mixin providing DB persistence and query methods for ChainComposer."""

    # Provided by main class
    _lock: object
    _chains: dict[str, ComposedChain]

    # ------------------------------------------------------------------
    #  Database
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        os.makedirs(_DB_DIR, exist_ok=True)
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(  # nosemgrep
                """
                CREATE TABLE IF NOT EXISTS composed_chains (
                    chain_id     TEXT PRIMARY KEY,
                    name         TEXT NOT NULL,
                    description  TEXT NOT NULL DEFAULT '',
                    steps        TEXT NOT NULL DEFAULT '[]',
                    metadata     TEXT NOT NULL DEFAULT '{}',
                    tenant_id    TEXT NOT NULL DEFAULT '',
                    created_at   REAL NOT NULL DEFAULT 0.0,
                    status       TEXT NOT NULL DEFAULT 'draft'
                )
                """
            )
            conn.execute(  # nosemgrep
                """
                CREATE TABLE IF NOT EXISTS chain_execution_log (
                    execution_id   TEXT PRIMARY KEY,
                    chain_id       TEXT NOT NULL,
                    success        INTEGER NOT NULL DEFAULT 0,
                    step_results   TEXT NOT NULL DEFAULT '[]',
                    total_duration_ms INTEGER NOT NULL DEFAULT 0,
                    failed_step    TEXT,
                    error          TEXT,
                    executed_at    REAL NOT NULL DEFAULT 0.0
                )
                """
            )
            conn.commit()

    def _load_chains(self) -> None:
        with sqlite3.connect(_DB_PATH) as conn:
            rows = conn.execute(  # nosemgrep
                "SELECT chain_id, name, description, steps, metadata, "
                "tenant_id, created_at, status FROM composed_chains"
            ).fetchall()

        for row in rows:
            chain_id = row[0]
            try:
                chain = ComposedChain(
                    chain_id=chain_id, name=row[1], description=row[2],
                    steps=self._deserialize_steps(json.loads(row[3]) if row[3] else []),
                    metadata=json.loads(row[4]) if row[4] else {},
                    tenant_id=row[5], created_at=row[6],
                    status=ChainStatus(row[7]) if row[7] else ChainStatus.DRAFT,
                )
                self._chains[chain_id] = chain
            except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
                import logging
                logging.getLogger(__name__).warning("Failed to load chain %s: %s", chain_id, exc)

    @staticmethod
    def _serialize_steps(steps: list[ChainStep]) -> str:
        return json.dumps([
            {"step_id": s.step_id,
             "step_type": s.step_type.value if isinstance(s.step_type, ChainStepType) else s.step_type,
             "config": s.config, "next_step_id": s.next_step_id,
             "condition_expr": s.condition_expr, "timeout_ms": s.timeout_ms,
             "retry_count": s.retry_count}
            for s in steps
        ])

    @staticmethod
    def _deserialize_steps(raw: list[dict[str, Any]]) -> list[ChainStep]:
        result: list[ChainStep] = []
        for s in raw:
            step_type_raw = s.get("step_type", "action")
            try:
                step_type = ChainStepType(step_type_raw)
            except ValueError:
                step_type = ChainStepType.ACTION
            result.append(ChainStep(
                step_id=s.get("step_id", ""), step_type=step_type,
                config=s.get("config", {}), next_step_id=s.get("next_step_id", ""),
                condition_expr=s.get("condition_expr", ""),
                timeout_ms=s.get("timeout_ms", 30000), retry_count=s.get("retry_count", 3),
            ))
        return result

    def _save_chain(self, chain: ComposedChain) -> None:
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(  # nosemgrep
                "INSERT OR REPLACE INTO composed_chains "
                "(chain_id, name, description, steps, metadata, tenant_id, created_at, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    chain.chain_id, chain.name, chain.description,
                    self._serialize_steps(chain.steps),
                    json.dumps(chain.metadata), chain.tenant_id,
                    chain.created_at,
                    chain.status.value if isinstance(chain.status, ChainStatus) else chain.status,
                ),
            )
            conn.commit()

    def _log_execution(self, result: ChainExecutionResult) -> None:
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"
        with sqlite3.connect(_DB_PATH) as conn:
            conn.execute(  # nosemgrep
                "INSERT INTO chain_execution_log "
                "(execution_id, chain_id, success, step_results, "
                "total_duration_ms, failed_step, error, executed_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    execution_id, result.chain_id,
                    1 if result.success else 0,
                    json.dumps([{"step_id": sr.step_id, "success": sr.success,
                                "output": sr.output, "duration_ms": sr.duration_ms,
                                "retry_count": sr.retry_count, "error": sr.error}
                               for sr in result.step_results]),
                    result.total_duration_ms, result.failed_step,
                    result.error, time.time(),
                ),
            )
            conn.commit()

    # ------------------------------------------------------------------
    #  Query
    # ------------------------------------------------------------------

    def get_chain(self, chain_id: str) -> ComposedChain | None:
        with self._lock:
            return self._chains.get(chain_id)

    def list_chains(self, tenant_id: str | None = None) -> list[ComposedChain]:
        with self._lock:
            chains = list(self._chains.values())
        if tenant_id:
            chains = [c for c in chains if c.tenant_id == tenant_id]
        return sorted(chains, key=lambda c: c.created_at, reverse=True)
