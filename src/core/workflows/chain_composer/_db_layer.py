"""
ZENIC-AGENTS — DynamicChainComposer: Database layer.

Standalone DB functions extracted from DynamicChainComposer.
These accept db_path / lock as parameters instead of using self.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from typing import Any

from ._types import (
    _DB_PATH,
    ChainExecutionResult,
    ChainStatus,
    ChainStep,
    ChainStepResult,
    ComposedChain,
)

logger = logging.getLogger(__name__)


# ── Schema creation ───────────────────────────────────────

def init_db(db_path: str = _DB_PATH) -> None:
    """Create the chains tables if they do not exist."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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
        conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
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


# ── Serialization helpers ─────────────────────────────────

def serialize_steps(steps: list[ChainStep]) -> str:
    """Serialize a list of ChainStep to JSON string."""
    from ._types import ChainStepType as _CST

    return json.dumps([
        {
            "step_id": s.step_id,
            "step_type": s.step_type.value if isinstance(s.step_type, _CST) else s.step_type,
            "config": s.config,
            "next_step_id": s.next_step_id,
            "condition_expr": s.condition_expr,
            "timeout_ms": s.timeout_ms,
            "retry_count": s.retry_count,
        }
        for s in steps
    ])


def deserialize_steps(raw: list[dict[str, Any]]) -> list[ChainStep]:
    """Deserialize a list of dicts into ChainStep objects."""
    from ._types import ChainStepType as _CST

    result: list[ChainStep] = []
    for s in raw:
        step_type_raw = s.get("step_type", "action")
        try:
            step_type = _CST(step_type_raw)
        except ValueError:
            step_type = _CST.ACTION
        result.append(ChainStep(
            step_id=s.get("step_id", ""),
            step_type=step_type,
            config=s.get("config", {}),
            next_step_id=s.get("next_step_id", ""),
            condition_expr=s.get("condition_expr", ""),
            timeout_ms=s.get("timeout_ms", 30000),
            retry_count=s.get("retry_count", 3),
        ))
    return result


# ── Load chains from DB ───────────────────────────────────

def load_chains(db_path: str = _DB_PATH) -> dict[str, ComposedChain]:
    """Load persisted chains from SQLite and return as a dict."""
    chains: dict[str, ComposedChain] = {}

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            "SELECT chain_id, name, description, steps, metadata, "
            "tenant_id, created_at, status FROM composed_chains"
        ).fetchall()

    for row in rows:
        chain_id = row[0]
        try:
            chain = ComposedChain(
                chain_id=chain_id,
                name=row[1],
                description=row[2],
                steps=deserialize_steps(json.loads(row[3]) if row[3] else []),
                metadata=json.loads(row[4]) if row[4] else {},
                tenant_id=row[5],
                created_at=row[6],
                status=ChainStatus(row[7]) if row[7] else ChainStatus.DRAFT,
            )
            chains[chain_id] = chain
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            logger.warning("Failed to load chain %s: %s", chain_id, exc)

    return chains


# ── Save chain to DB ──────────────────────────────────────

def save_chain(chain: ComposedChain, db_path: str = _DB_PATH) -> None:
    """Persist a single chain to SQLite."""
    with sqlite3.connect(db_path) as conn:
        conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            """
            INSERT OR REPLACE INTO composed_chains
                (chain_id, name, description, steps, metadata,
                 tenant_id, created_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chain.chain_id,
                chain.name,
                chain.description,
                serialize_steps(chain.steps),
                json.dumps(chain.metadata),
                chain.tenant_id,
                chain.created_at,
                chain.status.value if isinstance(chain.status, ChainStatus) else chain.status,
            ),
        )
        conn.commit()


# ── Log execution ─────────────────────────────────────────

def log_execution(result: ChainExecutionResult, db_path: str = _DB_PATH) -> None:
    """Record execution result to DB."""
    execution_id = f"exec_{uuid.uuid4().hex[:12]}"
    with sqlite3.connect(db_path) as conn:
        conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
            """
            INSERT INTO chain_execution_log
                (execution_id, chain_id, success, step_results,
                 total_duration_ms, failed_step, error, executed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                execution_id,
                result.chain_id,
                1 if result.success else 0,
                json.dumps([
                    {
                        "step_id": sr.step_id,
                        "success": sr.success,
                        "output": sr.output,
                        "duration_ms": sr.duration_ms,
                        "retry_count": sr.retry_count,
                        "error": sr.error,
                    }
                    for sr in result.step_results
                ]),
                result.total_duration_ms,
                result.failed_step,
                result.error,
                time.time(),
            ),
        )
        conn.commit()
