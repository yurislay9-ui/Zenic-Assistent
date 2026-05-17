from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .types import (
    PolicyCondition,
    PolicyDocument,
    PolicyEffect,
    PolicyOperator,
    PolicyStatement,
)

logger = logging.getLogger("zenic_agents.core.policy_code.engine")

DB_DIR = Path.home() / ".zenic_agents" / "db"
DB_PATH = DB_DIR / "policy_code.sqlite"


def _retry(func: Any, max_retries: int = 3, base_delay: float = 1.0) -> Any:
    for attempt in range(max_retries):
        try:
            return func()
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))


class PolicyEvaluationResult:
    __slots__ = (
        "allowed", "matched_policies", "denied_by",
        "conditions_met", "conditions_failed", "evaluation_time_ms",
    )

    def __init__(
        self,
        allowed: bool = False,
        matched_policies: Optional[List[str]] = None,
        denied_by: Optional[List[str]] = None,
        conditions_met: Optional[List[str]] = None,
        conditions_failed: Optional[List[str]] = None,
        evaluation_time_ms: float = 0.0,
    ) -> None:
        self.allowed = allowed
        self.matched_policies = matched_policies or []
        self.denied_by = denied_by or []
        self.conditions_met = conditions_met or []
        self.conditions_failed = conditions_failed or []
        self.evaluation_time_ms = evaluation_time_ms

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "matched_policies": self.matched_policies,
            "denied_by": self.denied_by,
            "conditions_met": self.conditions_met,
            "conditions_failed": self.conditions_failed,
            "evaluation_time_ms": round(self.evaluation_time_ms, 3),
        }


class PolicyCodeEngine:
    """Thread-safe policy evaluation engine with SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._policies: Dict[str, PolicyDocument] = {}
        self._db_path = db_path or str(DB_PATH)
        self._eval_count = 0
        self._init_db()

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

    def create_policy(self, doc: PolicyDocument) -> str:
        """Store a policy and return its ID."""
        with self._lock:
            valid, errors = self.validate_policy(doc)
            if not valid:
                raise ValueError(f"Invalid policy: {errors}")
            if doc.id in self._policies:
                raise ValueError(f"Policy already exists: {doc.id}")
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            doc.created_at = doc.created_at or now
            doc.updated_at = now
            self._policies[doc.id] = doc
            self._save_to_db(doc)
            logger.info("Policy created: %s", doc.id)
            return doc.id

    def update_policy(self, policy_id: str, doc: PolicyDocument) -> bool:
        with self._lock:
            if policy_id not in self._policies:
                return False
            valid, errors = self.validate_policy(doc)
            if not valid:
                raise ValueError(f"Invalid policy: {errors}")
            doc.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._policies[policy_id] = doc
            self._save_to_db(doc)
            return True

    def delete_policy(self, policy_id: str) -> bool:
        with self._lock:
            if policy_id not in self._policies:
                return False
            del self._policies[policy_id]
            self._delete_from_db(policy_id)
            return True

    def get_policy(self, policy_id: str) -> Optional[PolicyDocument]:
        with self._lock:
            return self._policies.get(policy_id)

    def evaluate(
        self, resource: str, action: str, context: Dict[str, Any]
    ) -> PolicyEvaluationResult:
        """Evaluate all enabled policies."""
        start = time.monotonic()
        with self._lock:
            self._eval_count += 1
            allowed = True
            matched: List[str] = []
            denied_by: List[str] = []
            cond_met: List[str] = []
            cond_failed: List[str] = []

            # Collect all matching statements sorted by priority (higher first)
            all_stmts: List[Tuple[str, PolicyStatement]] = []
            for pid, doc in self._policies.items():
                if not doc.enabled:
                    continue
                for stmt in doc.statements:
                    all_stmts.append((pid, stmt))

            all_stmts.sort(key=lambda x: x[1].priority, reverse=True)

            for pid, stmt in all_stmts:
                match, met, failed = self._match_statement(stmt, resource, action, context)
                if match:
                    matched.append(pid)
                    cond_met.extend(met)
                    cond_failed.extend(failed)
                    if stmt.effect == PolicyEffect.DENY:
                        allowed = False
                        denied_by.append(f"{pid}:{stmt.id}")
                    elif stmt.effect == PolicyEffect.ALLOW:
                        pass  # explicit allow
                    elif stmt.effect == PolicyEffect.CONDITIONAL:
                        if not met:
                            allowed = False
                            denied_by.append(f"{pid}:{stmt.id}")

            elapsed = (time.monotonic() - start) * 1000
            return PolicyEvaluationResult(
                allowed=allowed,
                matched_policies=matched,
                denied_by=denied_by,
                conditions_met=cond_met,
                conditions_failed=cond_failed,
                evaluation_time_ms=elapsed,
            )

    def evaluate_single(
        self,
        policy_id: str,
        resource: str,
        action: str,
        context: Dict[str, Any],
    ) -> PolicyEvaluationResult:
        """Evaluate a single policy."""
        start = time.monotonic()
        with self._lock:
            doc = self._policies.get(policy_id)
            if doc is None or not doc.enabled:
                return PolicyEvaluationResult(evaluation_time_ms=(time.monotonic() - start) * 1000)

            allowed = True
            matched: List[str] = []
            denied_by: List[str] = []
            cond_met: List[str] = []
            cond_failed: List[str] = []

            for stmt in doc.statements:
                match, met, failed = self._match_statement(stmt, resource, action, context)
                if match:
                    matched.append(stmt.id)
                    cond_met.extend(met)
                    cond_failed.extend(failed)
                    if stmt.effect == PolicyEffect.DENY:
                        allowed = False
                        denied_by.append(stmt.id)
                    elif stmt.effect == PolicyEffect.CONDITIONAL and not met:
                        allowed = False
                        denied_by.append(stmt.id)

            elapsed = (time.monotonic() - start) * 1000
            return PolicyEvaluationResult(
                allowed=allowed,
                matched_policies=matched,
                denied_by=denied_by,
                conditions_met=cond_met,
                conditions_failed=cond_failed,
                evaluation_time_ms=elapsed,
            )

    def _match_statement(
        self,
        statement: PolicyStatement,
        resource: str,
        action: str,
        context: Dict[str, Any],
    ) -> Tuple[bool, List[str], List[str]]:
        """Match a statement against resource/action/context."""
        if not self._resource_matches(statement.resource, resource):
            return (False, [], [])
        if not self._action_matches(statement.action, action):
            return (False, [], [])

        conditions_met: List[str] = []
        conditions_failed: List[str] = []
        for cond in statement.conditions:
            if self._evaluate_condition(cond, context):
                conditions_met.append(cond.field)
            else:
                conditions_failed.append(cond.field)

        return (True, conditions_met, conditions_failed)

    def _resource_matches(self, pattern: str, resource: str) -> bool:
        if pattern == "*":
            return True
        if pattern == resource:
            return True
        # Simple wildcard matching
        regex = pattern.replace("*", ".*").replace("?", ".")
        try:
            return bool(re.match(f"^{regex}$", resource))
        except re.error:
            return pattern == resource

    def _action_matches(self, pattern: str, action: str) -> bool:
        if pattern == "*":
            return True
        if pattern == action:
            return True
        regex = pattern.replace("*", ".*").replace("?", ".")
        try:
            return bool(re.match(f"^{regex}$", action))
        except re.error:
            return pattern == action

    def _evaluate_condition(
        self, condition: PolicyCondition, context: Dict[str, Any]
    ) -> bool:
        """Evaluate a single condition against context."""
        value = context.get(condition.field)
        target = condition.value

        try:
            op = condition.operator
            if op == PolicyOperator.EQ:
                return value == target
            elif op == PolicyOperator.NEQ:
                return value != target
            elif op == PolicyOperator.GT:
                return value is not None and value > target
            elif op == PolicyOperator.LT:
                return value is not None and value < target
            elif op == PolicyOperator.GTE:
                return value is not None and value >= target
            elif op == PolicyOperator.LTE:
                return value is not None and value <= target
            elif op == PolicyOperator.IN:
                return value in (target if isinstance(target, (list, set, tuple)) else [target])
            elif op == PolicyOperator.NOT_IN:
                return value not in (target if isinstance(target, (list, set, tuple)) else [target])
            elif op == PolicyOperator.CONTAINS:
                if isinstance(value, str) and isinstance(target, str):
                    return target in value
                if isinstance(value, (list, set, tuple)):
                    return target in value
                return False
            elif op == PolicyOperator.STARTS_WITH:
                return isinstance(value, str) and isinstance(target, str) and value.startswith(target)
            elif op == PolicyOperator.REGEX:
                if value is None:
                    return False
                return bool(re.search(target, str(value)))
            else:
                return False
        except (TypeError, re.error):
            return False

    def list_policies(self, enabled_only: bool = True) -> List[PolicyDocument]:
        with self._lock:
            policies = list(self._policies.values())
            if enabled_only:
                policies = [p for p in policies if p.enabled]
            return policies

    def enable_policy(self, policy_id: str) -> bool:
        with self._lock:
            doc = self._policies.get(policy_id)
            if doc is None:
                return False
            doc.enabled = True
            self._save_to_db(doc)
            return True

    def disable_policy(self, policy_id: str) -> bool:
        with self._lock:
            doc = self._policies.get(policy_id)
            if doc is None:
                return False
            doc.enabled = False
            self._save_to_db(doc)
            return True

    def import_policy(self, policy_json: str) -> str:
        """Import a policy from JSON string."""
        doc = self._json_to_policy(policy_json)
        if doc is None:
            raise ValueError("Invalid policy JSON")
        valid, errors = self.validate_policy(doc)
        if not valid:
            raise ValueError(f"Invalid policy: {errors}")
        return self.create_policy(doc)

    def export_policy(self, policy_id: str) -> str:
        """Export a policy to JSON string."""
        with self._lock:
            doc = self._policies.get(policy_id)
            if doc is None:
                raise ValueError(f"Policy not found: {policy_id}")
            return self._policy_to_json(doc)

    def validate_policy(self, doc: PolicyDocument) -> Tuple[bool, List[str]]:
        """Validate a policy document."""
        errors: List[str] = []
        if not doc.id:
            errors.append("Policy ID is required")
        if not doc.name:
            errors.append("Policy name is required")
        if not doc.version:
            errors.append("Policy version is required")
        stmt_ids: set = set()
        for stmt in doc.statements:
            if not stmt.id:
                errors.append("Statement ID is required")
            if stmt.id in stmt_ids:
                errors.append(f"Duplicate statement ID: {stmt.id}")
            stmt_ids.add(stmt.id)
            if not stmt.resource:
                errors.append(f"Statement {stmt.id}: resource is required")
            if not stmt.action:
                errors.append(f"Statement {stmt.id}: action is required")
            for cond in stmt.conditions:
                if not cond.field:
                    errors.append(f"Statement {stmt.id}: condition field is required")
        return (len(errors) == 0, errors)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            total_stmts = sum(len(p.statements) for p in self._policies.values())
            effect_counts: Dict[str, int] = {}
            for p in self._policies.values():
                for s in p.statements:
                    effect_counts[s.effect.value] = effect_counts.get(s.effect.value, 0) + 1
            return {
                "total_policies": len(self._policies),
                "enabled_policies": sum(1 for p in self._policies.values() if p.enabled),
                "total_statements": total_stmts,
                "effect_counts": effect_counts,
                "evaluation_count": self._eval_count,
            }


_engine_instance: Optional[PolicyCodeEngine] = None
_engine_lock = threading.Lock()


def get_policy_code_engine(db_path: Optional[str] = None) -> PolicyCodeEngine:
    global _engine_instance
    with _engine_lock:
        if _engine_instance is None:
            _engine_instance = PolicyCodeEngine(db_path=db_path)
        return _engine_instance


def reset_policy_code_engine() -> None:
    global _engine_instance
    with _engine_lock:
        _engine_instance = None
