"""Persistence mixin for PolicyCodeEngine."""

from __future__ import annotations
import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from ._types import DB_DIR, DB_PATH, PolicyDocument, PolicyStatement, PolicyCondition, PolicyEffect, PolicyOperator
from ._helpers import _retry

logger = logging.getLogger("zenic_agents.core.policy_code.engine")


class PolicyPersistenceMixin:
    """Mixin providing SQLite persistence for PolicyCodeEngine.

    Expects the host class to have ``_db_path`` and ``_policies``
    attributes.
    """

    def _init_db(self) -> None:
        DB_DIR.mkdir(parents=True, exist_ok=True)

        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE TABLE IF NOT EXISTS policies (
                    policy_id TEXT PRIMARY KEY,
                    policy_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )
            conn.commit()
            conn.close()

        _retry(_create)
        self._load_from_db()

    def _load_from_db(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM policies").fetchall()  # nosemgrep: sqlalchemy-execute-raw-query
            conn.close()
            for row in rows:
                doc = self._json_to_policy(row["policy_json"])
                if doc is not None:
                    doc.enabled = bool(row["enabled"])
                    self._policies[doc.id] = doc
        except Exception as exc:
            logger.error("Failed to load policies from DB: %s", exc)

    def _policy_to_json(self, doc: PolicyDocument) -> str:
        data = {
            "id": doc.id,
            "name": doc.name,
            "version": doc.version,
            "statements": [
                {
                    "id": s.id,
                    "effect": s.effect.value,
                    "resource": s.resource,
                    "action": s.action,
                    "conditions": [
                        {
                            "field": c.field,
                            "operator": c.operator.value,
                            "value": c.value,
                            "description": c.description,
                        }
                        for c in s.conditions
                    ],
                    "priority": s.priority,
                    "description": s.description,
                }
                for s in doc.statements
            ],
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
            "enabled": doc.enabled,
            "metadata": doc.metadata,
        }
        return json.dumps(data)

    def _json_to_policy(self, raw: str) -> Optional[PolicyDocument]:
        try:
            data = json.loads(raw)
            statements = []
            for s in data.get("statements", []):
                conditions = [
                    PolicyCondition(
                        field=c["field"],
                        operator=PolicyOperator(c["operator"]),
                        value=c.get("value"),
                        description=c.get("description", ""),
                    )
                    for c in s.get("conditions", [])
                ]
                statements.append(PolicyStatement(
                    id=s["id"],
                    effect=PolicyEffect(s["effect"]),
                    resource=s["resource"],
                    action=s["action"],
                    conditions=conditions,
                    priority=s.get("priority", 0),
                    description=s.get("description", ""),
                ))
            return PolicyDocument(
                id=data["id"],
                name=data["name"],
                version=data.get("version", "1.0"),
                statements=statements,
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                enabled=data.get("enabled", True),
                metadata=data.get("metadata", {}),
            )
        except Exception as exc:
            logger.error("Failed to parse policy JSON: %s", exc)
            return None

    def _save_to_db(self, doc: PolicyDocument) -> None:
        policy_json = self._policy_to_json(doc)
        now = time.time()

        def _upsert() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT OR REPLACE INTO policies
                   (policy_id, policy_json, enabled, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (doc.id, policy_json, int(doc.enabled), now, now),
            )
            conn.commit()
            conn.close()

        _retry(_upsert)

    def _delete_from_db(self, policy_id: str) -> None:
        def _del() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("DELETE FROM policies WHERE policy_id = ?", (policy_id,))  # nosemgrep: sqlalchemy-execute-raw-query
            conn.commit()
            conn.close()

        _retry(_del)
