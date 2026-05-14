"""
Zenic-Agents Asistente - Mode Capabilities (Phase 6.4)

Capability definitions for each system operating mode.
Extracted from manager.py for the 400-line limit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from ..manager import SystemMode


@dataclass
class ModeCapabilities:
    """Capabilities available in a specific mode."""
    mode: SystemMode
    can_read: bool = True
    can_write: bool = False
    can_delete: bool = False
    can_manage_users: bool = False
    can_change_config: bool = False
    can_approve_actions: bool = False
    can_export_data: bool = True
    can_import_data: bool = False
    can_send_email: bool = False
    can_create_invoice: bool = False
    can_process_payment: bool = False
    can_schedule: bool = False
    can_use_api: bool = True
    can_access_dashboard: bool = True
    max_actions_per_hour: int = 0
    allowed_endpoints: List[str] = field(default_factory=list)
    blocked_actions: List[str] = field(default_factory=list)


# ── Mode capability definitions ───────────────────────────

MODE_CAPABILITIES = {
    SystemMode.NORMAL: ModeCapabilities(
        mode=SystemMode.NORMAL,
        can_read=True, can_write=True, can_delete=True,
        can_manage_users=True, can_change_config=True,
        can_approve_actions=True, can_export_data=True,
        can_import_data=True, can_send_email=True,
        can_create_invoice=True, can_process_payment=True,
        can_schedule=True, can_use_api=True, can_access_dashboard=True,
        max_actions_per_hour=1000,
    ),
    SystemMode.RESTRICTIVE: ModeCapabilities(
        mode=SystemMode.RESTRICTIVE,
        can_read=True, can_write=True, can_delete=False,
        can_manage_users=False, can_change_config=False,
        can_approve_actions=True, can_export_data=True,
        can_import_data=False, can_send_email=True,
        can_create_invoice=True, can_process_payment=False,
        can_schedule=True, can_use_api=True, can_access_dashboard=True,
        max_actions_per_hour=500,
        blocked_actions=["manage_system", "change_config", "refund"],
    ),
    SystemMode.DEGRADED: ModeCapabilities(
        mode=SystemMode.DEGRADED,
        can_read=True, can_write=False, can_delete=False,
        can_manage_users=False, can_change_config=False,
        can_approve_actions=False, can_export_data=True,
        can_import_data=False, can_send_email=False,
        can_create_invoice=False, can_process_payment=False,
        can_schedule=False, can_use_api=True, can_access_dashboard=True,
        max_actions_per_hour=100,
        blocked_actions=["write", "delete", "manage_users", "change_config",
                         "send_email", "create_invoice", "process_payment"],
    ),
    SystemMode.PARALYSIS_L1: ModeCapabilities(
        mode=SystemMode.PARALYSIS_L1,
        can_read=True, can_write=False, can_delete=False,
        can_manage_users=False, can_change_config=False,
        can_approve_actions=False, can_export_data=True,
        can_import_data=False, can_send_email=False,
        can_create_invoice=False, can_process_payment=False,
        can_schedule=False, can_use_api=False, can_access_dashboard=True,
        max_actions_per_hour=20,
        blocked_actions=["write", "delete", "manage", "send", "create", "process"],
    ),
    SystemMode.PARALYSIS_L2: ModeCapabilities(
        mode=SystemMode.PARALYSIS_L2,
        can_read=True, can_write=False, can_delete=False,
        can_manage_users=False, can_change_config=False,
        can_approve_actions=False, can_export_data=True,
        can_import_data=False, can_send_email=False,
        can_create_invoice=False, can_process_payment=False,
        can_schedule=False, can_use_api=False, can_access_dashboard=False,
        max_actions_per_hour=5,
        blocked_actions=["write", "delete", "manage", "send", "create",
                         "process", "api", "schedule"],
        allowed_endpoints=["/health", "/api/v1/export", "/api/v1/status"],
    ),
    SystemMode.PARALYSIS_L3: ModeCapabilities(
        mode=SystemMode.PARALYSIS_L3,
        can_read=False, can_write=False, can_delete=False,
        can_manage_users=False, can_change_config=False,
        can_approve_actions=False, can_export_data=True,
        can_import_data=False, can_send_email=False,
        can_create_invoice=False, can_process_payment=False,
        can_schedule=False, can_use_api=False, can_access_dashboard=False,
        max_actions_per_hour=2,
        blocked_actions=["*"],
        allowed_endpoints=["/health", "/api/v1/export"],
    ),
}
