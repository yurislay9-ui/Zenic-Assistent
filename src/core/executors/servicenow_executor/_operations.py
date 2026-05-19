"""ZENIC-AGENTS - ServiceNow Executor: Operations Mixin"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ..base import ActionResult
from ._incident_mixin import _IncidentOpsMixin

logger = logging.getLogger(__name__)


class _OperationsMixin(_IncidentOpsMixin):
    """Mixin for ServiceNow operation methods.

    Inherits incident operations from _IncidentOpsMixin and adds
    comment and change-request operations.
    """

    async def _add_comment(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Add a comment (journal entry) to a ServiceNow incident.

        Required config: ``incident_id``, ``comment``.
        """
        start = self._measure()
        incident_id = config.get("incident_id", "")
        comment = config.get("comment", "")

        if not incident_id:
            return ActionResult(
                success=False,
                data={"operation": "add_comment"},
                error="incident_id is required for add_comment",
                duration_ms=self._elapsed_ms(start),
            )

        if not comment:
            return ActionResult(
                success=False,
                data={"operation": "add_comment", "incident_id": incident_id},
                error="comment is required for add_comment",
                duration_ms=self._elapsed_ms(start),
            )

        # ServiceNow: comments are added via the `comments` field on the incident
        payload: Dict[str, Any] = {
            "comments": comment,
        }

        additional = config.get("additional_fields", {})
        if isinstance(additional, dict):
            payload.update(additional)

        url = self._build_url(instance_url, "incident", sys_id=incident_id)
        resp = await self._snow_request("PATCH", url, headers, payload)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            result_data = body["result"]
            logger.info(
                "ServiceNowExecutor: added comment to incident %s",
                incident_id,
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "add_comment",
                    "incident_id": incident_id,
                    "comment": comment,
                    "record": result_data,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: add_comment failed for %s — %s",
            incident_id, error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "add_comment", "incident_id": incident_id, "status": status, "response": body},
            error=f"Failed to add comment to {incident_id}: {error_msg}",
            duration_ms=elapsed,
        )

    async def _create_change_request(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Create a new ServiceNow change request.

        Required config: ``short_description``.
        Optional: ``description``, ``priority``, ``category``,
            ``assignment_group``, ``additional_fields``.
        """
        start = self._measure()
        short_desc = config.get("short_description", "")

        if not short_desc:
            return ActionResult(
                success=False,
                data={"operation": "create_change_request"},
                error="short_description is required for create_change_request",
                duration_ms=self._elapsed_ms(start),
            )

        payload: Dict[str, Any] = {
            "short_description": short_desc,
        }

        for field_name in ("description", "priority", "category", "assignment_group"):
            value = config.get(field_name)
            if value is not None:
                payload[field_name] = value

        additional = config.get("additional_fields", {})
        if isinstance(additional, dict):
            payload.update(additional)

        url = self._build_url(instance_url, "change_request")
        resp = await self._snow_request("POST", url, headers, payload)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            result_data = body["result"]
            change_number = result_data.get("number", "unknown")
            logger.info(
                "ServiceNowExecutor: created change request %s (sys_id=%s)",
                change_number, result_data.get("sys_id", ""),
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "create_change_request",
                    "change_number": change_number,
                    "sys_id": result_data.get("sys_id", ""),
                    "record": result_data,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: create_change_request failed — %s", error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "create_change_request", "status": status, "response": body},
            error=f"Failed to create change request: {error_msg}",
            duration_ms=elapsed,
        )

    # ──────────────────────────────────────────────────────────
    #  DRY-RUN MODE
    # ──────────────────────────────────────────────────────────
