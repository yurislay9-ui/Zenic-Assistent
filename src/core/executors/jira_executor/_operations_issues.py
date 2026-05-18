"""ZENIC-AGENTS - Jira Executor: Issue CRUD Operations Mixin"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from ..base import ActionResult

logger = logging.getLogger(__name__)

_API_V2 = "/rest/api/2"


class _IssuesMixin:
    """Mixin for Jira issue CRUD operation methods."""

    async def _create_issue(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Create a new Jira issue.

        POST /rest/api/2/issue
        """
        project_key = config.get("project_key", "")
        if not project_key:
            return ActionResult(
                False, {"operation": "create_issue"},
                "Missing required config key: project_key",
            )

        summary = config.get("summary", "")
        if not summary:
            return ActionResult(
                False, {"operation": "create_issue"},
                "Missing required config key: summary",
            )

        issue_type = config.get("issue_type", "Task")
        description = config.get("description", "")
        priority = config.get("priority", "")
        labels = config.get("labels", [])
        assignee = config.get("assignee", "")
        additional = config.get("additional_fields", {})

        # Build fields dict
        fields: Dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }

        # Description — plain text for v2 API
        if description:
            fields["description"] = description

        # Priority
        if priority:
            fields["priority"] = {"name": priority}

        # Labels
        if labels and isinstance(labels, list):
            fields["labels"] = labels

        # Assignee
        if assignee:
            fields["assignee"] = {"name": assignee}

        # Merge additional fields (can override above)
        if additional and isinstance(additional, dict):
            fields.update(additional)

        url = f"{base_url}{_API_V2}/issue"
        resp = await self._jira_request("POST", url, headers, {"fields": fields})

        body = resp.get("body", {})
        status = resp.get("status", 0)

        if 200 <= status < 300 and body.get("key"):
            logger.info(
                "JiraExecutor: created issue %s in project %s",
                body["key"], project_key,
            )
            return ActionResult(
                True,
                {
                    "operation": "create_issue",
                    "issue_key": body.get("key", ""),
                    "issue_id": body.get("id", ""),
                    "self_link": body.get("self", ""),
                },
            )
        else:
            errors = body.get("errors", {})
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else str(errors)
            logger.warning(
                "JiraExecutor: create_issue failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {"operation": "create_issue", "status": status},
                f"Failed to create issue: {error_msg}",
            )

    # ── Operation: update_issue ────────────────────────────────

    async def _update_issue(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Update fields on an existing Jira issue.

        PUT /rest/api/2/issue/{issueKey}
        """
        issue_key = config.get("issue_key", "")
        if not issue_key:
            return ActionResult(
                False, {"operation": "update_issue"},
                "Missing required config key: issue_key",
            )

        fields: Dict[str, Any] = {}

        # Optional updatable fields
        for key in ("summary", "description"):
            val = config.get(key)
            if val is not None:
                fields[key] = val

        priority = config.get("priority")
        if priority:
            fields["priority"] = {"name": priority}

        labels = config.get("labels")
        if labels and isinstance(labels, list):
            fields["labels"] = labels

        assignee = config.get("assignee")
        if assignee:
            fields["assignee"] = {"name": assignee}

        issue_type = config.get("issue_type")
        if issue_type:
            fields["issuetype"] = {"name": issue_type}

        # Merge additional fields
        additional = config.get("additional_fields", {})
        if additional and isinstance(additional, dict):
            fields.update(additional)

        if not fields:
            return ActionResult(
                False, {"operation": "update_issue", "issue_key": issue_key},
                "No fields provided to update",
            )

        url = f"{base_url}{_API_V2}/issue/{issue_key}"
        resp = await self._jira_request("PUT", url, headers, {"fields": fields})

        status = resp.get("status", 0)

        if 200 <= status < 300:
            logger.info("JiraExecutor: updated issue %s", issue_key)
            return ActionResult(
                True,
                {"operation": "update_issue", "issue_key": issue_key},
            )
        else:
            body = resp.get("body", {})
            errors = body.get("errors", {})
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else str(errors)
            logger.warning(
                "JiraExecutor: update_issue failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {"operation": "update_issue", "issue_key": issue_key, "status": status},
                f"Failed to update issue: {error_msg}",
            )

    # ── Operation: get_issue ───────────────────────────────────

    async def _get_issue(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Retrieve a single Jira issue by key.

        GET /rest/api/2/issue/{issueKey}
        """
        issue_key = config.get("issue_key", "")
        if not issue_key:
            return ActionResult(
                False, {"operation": "get_issue"},
                "Missing required config key: issue_key",
            )

        fields_param = config.get("fields", [])
        params: Optional[Dict[str, Any]] = None
        if fields_param and isinstance(fields_param, list):
            params = {"fields": ",".join(fields_param)}

        url = f"{base_url}{_API_V2}/issue/{issue_key}"
        resp = await self._jira_request("GET", url, headers, params=params)

        body = resp.get("body", {})
        status = resp.get("status", 0)

        if 200 <= status < 300 and body.get("key"):
            logger.info("JiraExecutor: retrieved issue %s", issue_key)
            return ActionResult(
                True,
                {
                    "operation": "get_issue",
                    "issue_key": body.get("key", ""),
                    "issue_id": body.get("id", ""),
                    "fields": body.get("fields", {}),
                    "self_link": body.get("self", ""),
                },
            )
        else:
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: get_issue failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {"operation": "get_issue", "issue_key": issue_key, "status": status},
                f"Failed to get issue: {error_msg}",
            )

    # ── Operation: search_issues ───────────────────────────────

    async def _search_issues(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Search for issues using JQL.

        POST /rest/api/2/search
        """
        jql = config.get("jql", "")
        if not jql:
            return ActionResult(
                False, {"operation": "search_issues"},
                "Missing required config key: jql",
            )

        max_results = config.get("max_results", 50)
        fields_param = config.get("fields", ["summary", "status", "priority"])
        start_at = config.get("start_at", 0)

        payload: Dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
            "startAt": start_at,
            "fields": fields_param if isinstance(fields_param, list) else ["*all"],
        }

        url = f"{base_url}{_API_V2}/search"
        resp = await self._jira_request("POST", url, headers, payload)

        body = resp.get("body", {})
        status = resp.get("status", 0)

        if 200 <= status < 300:
            issues = body.get("issues", [])
            total = body.get("total", 0)
            logger.info(
                "JiraExecutor: search returned %d/%d issues",
                len(issues), total,
            )
            return ActionResult(
                True,
                {
                    "operation": "search_issues",
                    "issues": issues,
                    "total": total,
                    "max_results": max_results,
                    "start_at": start_at,
                    "returned": len(issues),
                },
            )
        else:
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: search_issues failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {"operation": "search_issues", "status": status},
                f"Failed to search issues: {error_msg}",
            )
