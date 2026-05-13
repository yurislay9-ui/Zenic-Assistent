"""TenantMixin usage tracking methods: recording, quotas, features, storage."""

from ._plans import PLAN_DEFINITIONS
from .._imports import (
    logger, sqlite3, json, threading,
    datetime, timezone,
)
from typing import Dict, List, Optional, Any


class TenantUsageMixin:
    """Usage tracking, quota checking, feature access, and storage quota."""

    def record_usage(
        self,
        tenant_id: str,
        requests: int = 1,
        tokens: int = 0,
        compute_seconds: float = 0.0,
    ) -> bool:
        """Record usage for a tenant on the current date (upsert)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        c = self._conn()
        try:
            with self._lock:
                c.execute(
                    "INSERT INTO tenant_usage (tenant_id, date, requests_count, tokens_count, compute_seconds) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(tenant_id, date) DO UPDATE SET "
                    "requests_count = requests_count + ?, "
                    "tokens_count = tokens_count + ?, "
                    "compute_seconds = compute_seconds + ?",
                    (tenant_id, today, requests, tokens, compute_seconds,
                     requests, tokens, compute_seconds),
                )
                c.commit()
            return True
        except sqlite3.Error as e:
            logger.error("AuthService: record_usage error: %s", e)
            return False

    def get_tenant_usage(self, tenant_id: str, date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get usage for a tenant on a specific date (default: today)."""
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        c = self._conn()
        try:
            row = c.execute(
                "SELECT tenant_id, date, requests_count, tokens_count, compute_seconds, storage_mb "
                "FROM tenant_usage WHERE tenant_id = ? AND date = ?",
                (tenant_id, date),
            ).fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error("AuthService: get_tenant_usage error: %s", e)
            return None

    def check_tenant_quota(self, tenant_id: str) -> Dict[str, Any]:
        """Check if tenant has exceeded any quota. Returns quota status."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"allowed": False, "error": "Tenant not found"}

        plan = tenant.get("plan", "free")
        quotas = PLAN_DEFINITIONS.get(plan, PLAN_DEFINITIONS["free"])
        usage = self.get_tenant_usage(tenant_id) or {
            "requests_count": 0,
            "tokens_count": 0,
            "compute_seconds": 0.0,
        }

        max_rpm = quotas.get("max_requests_per_minute", 10)
        max_rpd = quotas.get("max_requests_per_day", 500)
        max_tpd = quotas.get("max_tokens_per_day", 50000)

        requests_today = usage.get("requests_count", 0)
        tokens_today = usage.get("tokens_count", 0)

        if requests_today >= max_rpd:
            return {
                "allowed": False,
                "reason": f"Daily request limit reached ({requests_today}/{max_rpd})",
                "plan": plan,
                "usage": usage,
                "quotas": quotas,
            }
        if tokens_today >= max_tpd:
            return {
                "allowed": False,
                "reason": f"Daily token limit reached ({tokens_today}/{max_tpd})",
                "plan": plan,
                "usage": usage,
                "quotas": quotas,
            }
        return {
            "allowed": True,
            "plan": plan,
            "usage": usage,
            "quotas": quotas,
            "remaining_requests": max_rpd - requests_today,
            "remaining_tokens": max_tpd - tokens_today,
        }

    def get_tenant_features(self, tenant_id: str) -> List[str]:
        """Get feature list for tenant's plan."""
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return []
        plan = tenant.get("plan", "free")
        quotas = PLAN_DEFINITIONS.get(plan, PLAN_DEFINITIONS["free"])
        features = quotas.get("features", [])
        if features == "all":
            # Enterprise gets everything
            all_features = set()
            for pq in PLAN_DEFINITIONS.values():
                f = pq.get("features", [])
                if isinstance(f, list):
                    all_features.update(f)
            return sorted(all_features)
        return features if isinstance(features, list) else []

    def check_storage_quota(self, tenant_id: str) -> Dict[str, Any]:
        """Check if tenant has exceeded storage quota.

        Queries SmartMemory.get_tenant_usage_mb() and compares against
        the plan's max_storage_mb limit.

        Returns:
            Dict with 'allowed', 'used_mb', 'max_mb', 'remaining_mb'.
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"allowed": False, "error": "Tenant not found"}

        plan = tenant.get("plan", "free")
        quotas = PLAN_DEFINITIONS.get(plan, PLAN_DEFINITIONS["free"])
        max_mb = quotas.get("max_storage_mb", 50)

        used_mb = 0.0
        try:
            from src.core.smart_memory import SmartMemory
            sm = SmartMemory()
            used_mb = sm.get_tenant_usage_mb(tenant_id)
        except Exception as e:
            logger.debug("Storage quota check: SmartMemory unavailable: %s", e)

        remaining_mb = max(0, max_mb - used_mb)
        allowed = used_mb < max_mb

        return {
            "allowed": allowed,
            "used_mb": round(used_mb, 2),
            "max_mb": max_mb,
            "remaining_mb": round(remaining_mb, 2),
            "plan": plan,
        }
