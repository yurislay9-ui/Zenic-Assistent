"""Confirm Manager — Core implementation (composed from mixins)."""

from __future__ import annotations

from ._mixin_core import ConfirmManagerCoreMixin
from ._mixin_query import ConfirmManagerQueryMixin


class ConfirmManager(ConfirmManagerCoreMixin, ConfirmManagerQueryMixin):
    """Manages confirmation/approval flow for SafetyGate-flagged actions.

    Thread-safe. SQLite-backed with TTL auto-expiry.
    Integrates with SafetyGate.confirm_action() and SafetyGate.approve_action().
    """


__all__ = ["ConfirmManager"]
