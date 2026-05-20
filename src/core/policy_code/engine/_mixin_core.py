"""Core logic for engine."""

from __future__ import annotations
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from ._types import DB_DIR, DB_PATH, PolicyDocument, PolicyStatement, PolicyCondition, PolicyEffect, PolicyOperator, PolicyEvaluationResult
from ._helpers import _retry
from ._mixin_persistence import PolicyPersistenceMixin

logger = logging.getLogger("zenic_agents.core.policy_code.engine")

class PolicyCodeEngine(PolicyPersistenceMixin):
    """Thread-safe policy evaluation engine with SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._policies: Dict[str, PolicyDocument] = {}
        self._db_path = db_path or str(DB_PATH)
        self._eval_count = 0
        self._init_db()

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
