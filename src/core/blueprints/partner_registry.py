"""
Zenic-Agents Asistente - Partner Registry (Phase 5)

Registry for partner accounts that create and publish Blueprints.
Tracks certification status and revenue sharing.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from .types import PartnerInfo

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  PARTNER REGISTRY
# ──────────────────────────────────────────────────────────────

class PartnerRegistry:
    """Registry of partner accounts for Blueprint revenue sharing.

    Usage:
        registry = PartnerRegistry()
        info = registry.register_partner("p1", "Acme Corp", revenue_share_pct=15.0)
        registry.certify_partner("p1")
        registry.record_revenue("p1", 1000)
    """

    def __init__(self) -> None:
        self._partners: Dict[str, PartnerInfo] = {}
        self._revenue: Dict[str, int] = {}  # partner_id → cents earned

    def register_partner(
        self,
        partner_id: str,
        partner_name: str,
        revenue_share_pct: float = 0.0,
    ) -> PartnerInfo:
        """Register a new partner."""
        info = PartnerInfo(
            partner_id=partner_id,
            partner_name=partner_name,
            revenue_share_pct=revenue_share_pct,
            created_at=time.time(),
        )
        self._partners[partner_id] = info
        self._revenue[partner_id] = 0
        logger.info("PartnerRegistry: Registered partner %s", partner_name)
        return info

    def get_partner(self, partner_id: str) -> Optional[PartnerInfo]:
        """Get partner information."""
        return self._partners.get(partner_id)

    def certify_partner(self, partner_id: str) -> bool:
        """Mark a partner as certified (allowed to publish Blueprints)."""
        info = self._partners.get(partner_id)
        if info:
            info.certified = True
            return True
        return False

    def is_certified_partner(self, partner_id: str) -> bool:
        """Check if a partner is certified."""
        info = self._partners.get(partner_id)
        return info.certified if info else False

    def record_revenue(self, partner_id: str, amount_cents: int) -> None:
        """Record revenue for a partner."""
        if partner_id in self._revenue:
            self._revenue[partner_id] += amount_cents

    def get_revenue(self, partner_id: str) -> int:
        """Get total revenue for a partner (in cents)."""
        return self._revenue.get(partner_id, 0)

    def list_partners(self) -> List[Dict[str, Any]]:
        """List all registered partners."""
        results = []
        for pid, info in self._partners.items():
            results.append({
                "partner_id": pid,
                "name": info.partner_name,
                "revenue_share_pct": info.revenue_share_pct,
                "certified": info.certified,
                "total_revenue_cents": self._revenue.get(pid, 0),
            })
        return results
