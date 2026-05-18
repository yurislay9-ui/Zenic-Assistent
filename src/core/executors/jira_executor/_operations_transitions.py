"""ZENIC-AGENTS - Jira Executor: Transition Operations Mixin"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..base import ActionResult

logger = logging.getLogger(__name__)

_API_V2 = "/rest/api/2"


class _TransitionsMixin:
    """Mixin for Jira transition operation methods."""

    # ── Operation: transition_issue ────────────────────────────

    async def _transition_issue(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Transition an issue to a new status.

        POST /rest/api/2/issue/{issueKey}/transitions

        Accepts either transition_id or transition_name.
        When transition_name is provided, the available transitions
        are fetched first and matched by name.
        """
        issue_key = config.get("issue_key", "")
        if not issue_key:
            return ActionResult(
                False, {"operation": "transition_issue"},
                "Missing required config key: issue_key",
            )

        transition_id = config.get("transition_id", "")
        transition_name = config.get("transition_name", "")

        if not transition_id and not transition_name:
            return ActionResult(
                False, {"operation": "transition_issue", "issue_key": issue_key},
                "Either transition_id or transition_name is required",
            )

        # If only name given, resolve to ID
        if not transition_id and transition_name:
            trans_resp = await self._jira_request(
                "GET",
                f"{base_url}{_API_V2}/issue/{issue_key}/transitions",
                headers,
            )
            body = trans_resp.get("body", {})
            transitions = body.get("transitions", [])
            found_id = self._find_transition_by_name(transitions, transition_name)
            if found_id is None:
                available = [
                    {"id": t.get("id"), "name": t.get("name")}
                    for t in transitions
                ]
                return ActionResult(
                    False,
                    {
                        "operation": "transition_issue",
                        "issue_key": issue_key,
                        "available_transitions": available,
                    },
                    f"Transition '{transition_name}' not found for issue {issue_key}",
                )
            transition_id = found_id

        payload: Dict[str, Any] = {
            "transition": {"id": transition_id},
        }

        # Optional fields on transition (e.g. resolution)
        additional = config.get("additional_fields", {})
        if additional and isinstance(additional, dict):
            payload["fields"] = additional

        url = f"{base_url}{_API_V2}/issue/{issue_key}/transitions"
        resp = await self._jira_request("POST", url, headers, payload)

        status = resp.get("status", 0)

        if 200 <= status < 300:
            logger.info(
                "JiraExecutor: transitioned issue %s with transition %s",
                issue_key, transition_id,
            )
            return ActionResult(
                True,
                {
                    "operation": "transition_issue",
                    "issue_key": issue_key,
                    "transition_id": transition_id,
                },
            )
        else:
            body = resp.get("body", {})
            messages = body.get("errorMessages", [])
            errors = body.get("errors", {})
            error_msg = "; ".join(messages) if messages else str(errors)
            logger.warning(
                "JiraExecutor: transition_issue failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {
                    "operation": "transition_issue",
                    "issue_key": issue_key,
                    "status": status,
                },
                f"Failed to transition issue: {error_msg}",
            )

    # ── Operation: get_transitions ─────────────────────────────

    async def _get_transitions(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Get available transitions for an issue.

        GET /rest/api/2/issue/{issueKey}/transitions
        """
        issue_key = config.get("issue_key", "")
        if not issue_key:
            return ActionResult(
                False, {"operation": "get_transitions"},
                "Missing required config key: issue_key",
            )

        url = f"{base_url}{_API_V2}/issue/{issue_key}/transitions"
        resp = await self._jira_request("GET", url, headers)

        body = resp.get("body", {})
        status = resp.get("status", 0)

        if 200 <= status < 300:
            transitions = body.get("transitions", [])
            logger.info(
                "JiraExecutor: retrieved %d transitions for issue %s",
                len(transitions), issue_key,
            )
            return ActionResult(
                True,
                {
                    "operation": "get_transitions",
                    "issue_key": issue_key,
                    "transitions": [
                        {
                            "id": t.get("id", ""),
                            "name": t.get("name", ""),
                            "to": t.get("to", {}).get("name", ""),
                        }
                        for t in transitions
                    ],
                },
            )
        else:
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: get_transitions failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {
                    "operation": "get_transitions",
                    "issue_key": issue_key,
                    "status": status,
                },
                f"Failed to get transitions: {error_msg}",
            )

    # ── Utility: find transition by name ───────────────────────

    @staticmethod

    def _find_transition_by_name(
        transitions: List[Dict[str, Any]],
        name: str,
    ) -> Optional[str]:
        """Find a transition ID by its name (case-insensitive).

        Args:
            transitions: List of transition dicts from the API.
            name: Transition name to search for.

        Returns:
            Transition ID if found, else None.
        """
        name_lower = name.lower()
        for t in transitions:
            t_name = t.get("name", "")
            if t_name.lower() == name_lower:
                return t.get("id")
        return None
