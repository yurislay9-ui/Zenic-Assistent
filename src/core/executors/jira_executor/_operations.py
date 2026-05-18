"""ZENIC-AGENTS - Jira Executor: Operations Mixin (re-export shim)

This module composes the full _OperationsMixin from the split sub-modules:
  - _operations_issues      → issue CRUD (create, update, get, search)
  - _operations_transitions → transition operations (transition, get_transitions)
  - _operations_extras      → comments, links, metadata, dry-run
"""

from __future__ import annotations

from ._operations_issues import _IssuesMixin
from ._operations_transitions import _TransitionsMixin
from ._operations_extras import _ExtrasMixin


class _OperationsMixin(_IssuesMixin, _TransitionsMixin, _ExtrasMixin):
    """Combined mixin for all Jira CRUD operation methods."""

    pass


__all__ = ["_OperationsMixin"]
