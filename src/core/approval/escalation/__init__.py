"""
Zenic-Agents Asistente - Escalation with SLAs (Phase 5)

SLA-based auto-escalation for approval requests. If no decision is made
within the SLA window, the request is automatically escalated to the
next level in the hierarchy.

Escalation levels:
  L0_DIRECT (0):    reviewer      — 60min SLA, auto_escalate=True
  L1_TEAM_LEAD (1): team_lead     — 120min SLA, auto_escalate=True
  L2_DIRECTOR (2):  director      — 240min SLA, auto_escalate=True
  L3_C_SUITE (3):   c_suite       — no limit, auto_escalate=False

Integration:
  - Called by the approval engine when creating requests.
  - Notifies via NotificationDispatcher on escalation.

Persistence: SQLite with retry logic.
"""

from ._types import EscalationLevel, SLAPolicy, EscalationSLA
from ._escalator import EscalationManager
from ._routing import get_escalation_manager, reset_escalation_manager

__all__ = [
    "EscalationLevel",
    "SLAPolicy",
    "EscalationSLA",
    "EscalationManager",
    "get_escalation_manager",
    "reset_escalation_manager",
]
