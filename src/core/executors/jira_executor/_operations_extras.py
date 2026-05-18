"""ZENIC-AGENTS - Jira Executor: Extra Operations Mixin (comments, links, metadata, dry-run)"""

from __future__ import annotations

import logging
from typing import Any, Dict

from ..base import ActionResult

logger = logging.getLogger(__name__)

_API_V2 = "/rest/api/2"


class _ExtrasMixin:
    """Mixin for Jira comment, link, metadata, and dry-run methods."""

    # ── Operation: add_comment ─────────────────────────────────

    async def _add_comment(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Add a comment to an existing issue.

        POST /rest/api/2/issue/{issueKey}/comment
        """
        issue_key = config.get("issue_key", "")
        if not issue_key:
            return ActionResult(
                False, {"operation": "add_comment"},
                "Missing required config key: issue_key",
            )

        comment = config.get("comment", "")
        if not comment:
            return ActionResult(
                False, {"operation": "add_comment", "issue_key": issue_key},
                "Missing required config key: comment",
            )

        payload: Dict[str, Any] = {"body": comment}

        url = f"{base_url}{_API_V2}/issue/{issue_key}/comment"
        resp = await self._jira_request("POST", url, headers, payload)

        body = resp.get("body", {})
        status = resp.get("status", 0)

        if 200 <= status < 300:
            comment_id = body.get("id", "")
            logger.info(
                "JiraExecutor: added comment %s to issue %s",
                comment_id, issue_key,
            )
            return ActionResult(
                True,
                {
                    "operation": "add_comment",
                    "issue_key": issue_key,
                    "comment_id": comment_id,
                    "comment_self": body.get("self", ""),
                },
            )
        else:
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: add_comment failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {
                    "operation": "add_comment",
                    "issue_key": issue_key,
                    "status": status,
                },
                f"Failed to add comment: {error_msg}",
            )

    # ── Operation: link_issues ─────────────────────────────────

    async def _link_issues(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Create a link between two issues.

        POST /rest/api/2/issueLink
        """
        link_type = config.get("link_type", "Blocks")
        inward_issue = config.get("inward_issue", "")
        outward_issue = config.get("outward_issue", "")

        if not inward_issue:
            return ActionResult(
                False, {"operation": "link_issues"},
                "Missing required config key: inward_issue",
            )
        if not outward_issue:
            return ActionResult(
                False, {"operation": "link_issues"},
                "Missing required config key: outward_issue",
            )

        payload: Dict[str, Any] = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_issue},
            "outwardIssue": {"key": outward_issue},
        }

        comment = config.get("comment", "")
        if comment:
            payload["comment"] = {"body": comment}

        url = f"{base_url}{_API_V2}/issueLink"
        resp = await self._jira_request("POST", url, headers, payload)

        status = resp.get("status", 0)

        if 200 <= status < 300:
            logger.info(
                "JiraExecutor: linked %s -> %s (%s)",
                inward_issue, outward_issue, link_type,
            )
            return ActionResult(
                True,
                {
                    "operation": "link_issues",
                    "link_type": link_type,
                    "inward_issue": inward_issue,
                    "outward_issue": outward_issue,
                },
            )
        else:
            body = resp.get("body", {})
            messages = body.get("errorMessages", [])
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: link_issues failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {
                    "operation": "link_issues",
                    "status": status,
                    "inward_issue": inward_issue,
                    "outward_issue": outward_issue,
                },
                f"Failed to link issues: {error_msg}",
            )

    # ── Operation: get_issue_types ─────────────────────────────

    async def _get_issue_types(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Get all issue types available to the user.

        GET /rest/api/2/issuetype
        """
        url = f"{base_url}{_API_V2}/issuetype"
        resp = await self._jira_request("GET", url, headers)

        body = resp.get("body", {})
        status = resp.get("status", 0)

        # Body may be a list directly
        if isinstance(body, list):
            issue_types = body
        else:
            issue_types = []

        if 200 <= status < 300 and isinstance(issue_types, list):
            logger.info(
                "JiraExecutor: retrieved %d issue types",
                len(issue_types),
            )
            return ActionResult(
                True,
                {
                    "operation": "get_issue_types",
                    "issue_types": [
                        {
                            "id": it.get("id", ""),
                            "name": it.get("name", ""),
                            "subtask": it.get("subtask", False),
                            "description": it.get("description", ""),
                        }
                        for it in issue_types
                    ],
                },
            )
        else:
            messages = body.get("errorMessages", []) if isinstance(body, dict) else []
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: get_issue_types failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {"operation": "get_issue_types", "status": status},
                f"Failed to get issue types: {error_msg}",
            )

    # ── Operation: get_priorities ──────────────────────────────

    async def _get_priorities(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        base_url: str,
    ) -> ActionResult:
        """Get all priorities.

        GET /rest/api/2/priority
        """
        url = f"{base_url}{_API_V2}/priority"
        resp = await self._jira_request("GET", url, headers)

        body = resp.get("body", {})
        status = resp.get("status", 0)

        if isinstance(body, list):
            priorities = body
        else:
            priorities = []

        if 200 <= status < 300 and isinstance(priorities, list):
            logger.info(
                "JiraExecutor: retrieved %d priorities",
                len(priorities),
            )
            return ActionResult(
                True,
                {
                    "operation": "get_priorities",
                    "priorities": [
                        {
                            "id": p.get("id", ""),
                            "name": p.get("name", ""),
                            "statusColor": p.get("statusColor", ""),
                        }
                        for p in priorities
                    ],
                },
            )
        else:
            messages = body.get("errorMessages", []) if isinstance(body, dict) else []
            error_msg = "; ".join(messages) if messages else f"HTTP {status}"
            logger.warning(
                "JiraExecutor: get_priorities failed (HTTP %d): %s",
                status, error_msg,
            )
            return ActionResult(
                False,
                {"operation": "get_priorities", "status": status},
                f"Failed to get priorities: {error_msg}",
            )

    # ── Dry-Run Mode ──────────────────────────────────────────

    def _dry_run(self, config: Dict[str, Any]) -> ActionResult:
        """Return a simulated result when Jira is not configured.

        Logs the intended operation and returns success with dry_run flag.
        """
        operation = config.get("operation", "unknown")
        project_key = config.get("project_key", "")
        issue_key = config.get("issue_key", "")
        summary = config.get("summary", "")
        jql = config.get("jql", "")
        comment = config.get("comment", "")

        logger.info(
            "[JIRA DRY-RUN] operation=%s project=%s issue=%s "
            "summary=%.80s jql=%.80s comment=%.80s",
            operation, project_key, issue_key, summary, jql, comment,
        )

        data: Dict[str, Any] = {
            "operation": operation,
            "mode": "dry_run",
        }

        # Add operation-specific preview data
        if operation == "create_issue":
            data["would_create"] = {
                "project_key": project_key,
                "summary": summary,
                "issue_type": config.get("issue_type", "Task"),
                "priority": config.get("priority", ""),
            }
        elif operation in ("update_issue", "transition_issue", "get_issue",
                           "add_comment", "get_transitions"):
            data["issue_key"] = issue_key
        elif operation == "search_issues":
            data["jql"] = jql
        elif operation == "link_issues":
            data["inward_issue"] = config.get("inward_issue", "")
            data["outward_issue"] = config.get("outward_issue", "")
            data["link_type"] = config.get("link_type", "Blocks")

        return ActionResult(True, data)
