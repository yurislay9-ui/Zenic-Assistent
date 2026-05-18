"""ZENIC-AGENTS - ServiceNow Executor: Operations Mixin"""

from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Dict, List, Optional

from ..base import ActionResult

logger = logging.getLogger(__name__)


class _OperationsMixin:
    """Mixin for ServiceNow operation methods."""

    async def _create_incident(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Create a new ServiceNow incident.

        Required config: ``short_description``.
        Optional: ``description``, ``priority``, ``severity``,
            ``category``, ``assignment_group``, ``additional_fields``.
        """
        start = self._measure()
        short_desc = config.get("short_description", "")

        if not short_desc:
            return ActionResult(
                success=False,
                data={"operation": "create_incident"},
                error="short_description is required for create_incident",
                duration_ms=self._elapsed_ms(start),
            )

        # Build incident payload
        payload: Dict[str, Any] = {
            "short_description": short_desc,
        }

        for field_name in ("description", "priority", "severity", "category", "assignment_group"):
            value = config.get(field_name)
            if value is not None:
                payload[field_name] = value

        # Merge additional fields
        additional = config.get("additional_fields", {})
        if isinstance(additional, dict):
            payload.update(additional)

        url = self._build_url(instance_url, "incident")
        resp = await self._snow_request("POST", url, headers, payload)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            result_data = body["result"]
            incident_number = result_data.get("number", "unknown")
            logger.info(
                "ServiceNowExecutor: created incident %s (sys_id=%s)",
                incident_number, result_data.get("sys_id", ""),
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "create_incident",
                    "incident_number": incident_number,
                    "sys_id": result_data.get("sys_id", ""),
                    "record": result_data,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: create_incident failed — %s", error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "create_incident", "status": status, "response": body},
            error=f"Failed to create incident: {error_msg}",
            duration_ms=elapsed,
        )

    async def _update_incident(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Update an existing ServiceNow incident.

        Required config: ``incident_id``.
        """
        start = self._measure()
        incident_id = config.get("incident_id", "")

        if not incident_id:
            return ActionResult(
                success=False,
                data={"operation": "update_incident"},
                error="incident_id is required for update_incident",
                duration_ms=self._elapsed_ms(start),
            )

        # Build update payload from provided fields
        payload: Dict[str, Any] = {}

        for field_name in (
            "short_description", "description", "priority", "severity",
            "category", "assignment_group", "state",
        ):
            value = config.get(field_name)
            if value is not None:
                payload[field_name] = value

        additional = config.get("additional_fields", {})
        if isinstance(additional, dict):
            payload.update(additional)

        if not payload:
            return ActionResult(
                success=False,
                data={"operation": "update_incident", "incident_id": incident_id},
                error="No fields provided to update",
                duration_ms=self._elapsed_ms(start),
            )

        url = self._build_url(instance_url, "incident", sys_id=incident_id)
        resp = await self._snow_request("PATCH", url, headers, payload)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            result_data = body["result"]
            logger.info(
                "ServiceNowExecutor: updated incident %s",
                incident_id,
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "update_incident",
                    "incident_id": incident_id,
                    "record": result_data,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: update_incident failed for %s — %s",
            incident_id, error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "update_incident", "incident_id": incident_id, "status": status, "response": body},
            error=f"Failed to update incident {incident_id}: {error_msg}",
            duration_ms=elapsed,
        )

    async def _close_incident(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Close a ServiceNow incident.

        Required config: ``incident_id``.
        Sets ``state`` to 7 (Closed) by default; can be overridden via
        ``state`` in config.
        """
        start = self._measure()
        incident_id = config.get("incident_id", "")

        if not incident_id:
            return ActionResult(
                success=False,
                data={"operation": "close_incident"},
                error="incident_id is required for close_incident",
                duration_ms=self._elapsed_ms(start),
            )

        close_state = config.get("state", _STATE_CLOSED)

        payload: Dict[str, Any] = {
            "state": close_state,
        }

        # Include close notes if provided
        close_notes = config.get("close_notes", config.get("comment", ""))
        if close_notes:
            payload["close_notes"] = close_notes

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
                "ServiceNowExecutor: closed incident %s (state=%s)",
                incident_id, result_data.get("state", close_state),
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "close_incident",
                    "incident_id": incident_id,
                    "state": result_data.get("state", close_state),
                    "record": result_data,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: close_incident failed for %s — %s",
            incident_id, error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "close_incident", "incident_id": incident_id, "status": status, "response": body},
            error=f"Failed to close incident {incident_id}: {error_msg}",
            duration_ms=elapsed,
        )

    async def _get_incident(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Retrieve a single ServiceNow incident by ID.

        Required config: ``incident_id``.
        Optional: ``fields`` — list of field names to return.
        """
        start = self._measure()
        incident_id = config.get("incident_id", "")

        if not incident_id:
            return ActionResult(
                success=False,
                data={"operation": "get_incident"},
                error="incident_id is required for get_incident",
                duration_ms=self._elapsed_ms(start),
            )

        url = self._build_url(instance_url, "incident", sys_id=incident_id)

        # Add sysparm_fields if specified
        fields = config.get("fields", [])
        if fields and isinstance(fields, (list, tuple)):
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}sysparm_fields={','.join(str(f) for f in fields)}"

        resp = await self._snow_request("GET", url, headers)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            result_data = body["result"]
            logger.info(
                "ServiceNowExecutor: retrieved incident %s",
                incident_id,
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "get_incident",
                    "incident_id": incident_id,
                    "record": result_data,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: get_incident failed for %s — %s",
            incident_id, error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "get_incident", "incident_id": incident_id, "status": status, "response": body},
            error=f"Failed to get incident {incident_id}: {error_msg}",
            duration_ms=elapsed,
        )

    async def _search_incidents(
        self,
        config: Dict[str, Any],
        headers: Dict[str, str],
        instance_url: str,
    ) -> ActionResult:
        """Search ServiceNow incidents using an encoded query.

        Required config: ``search_query`` (ServiceNow encoded query string).
        Optional: ``fields`` — list of field names to return.
        """
        start = self._measure()
        search_query = config.get("search_query", "")

        if not search_query:
            return ActionResult(
                success=False,
                data={"operation": "search_incidents"},
                error="search_query is required for search_incidents",
                duration_ms=self._elapsed_ms(start),
            )

        url = self._build_url(instance_url, "incident")

        # Build query parameters
        params: List[str] = [
            f"sysparm_query={urllib.parse.quote(search_query, safe='')}",
        ]

        fields = config.get("fields", [])
        if fields and isinstance(fields, (list, tuple)):
            params.append(f"sysparm_fields={','.join(str(f) for f in fields)}")

        # Limit results to prevent huge responses
        limit = config.get("limit", 100)
        if isinstance(limit, int) and limit > 0:
            params.append(f"sysparm_limit={min(limit, 1000)}")

        url = f"{url}?{'&'.join(params)}"

        resp = await self._snow_request("GET", url, headers)

        elapsed = self._elapsed_ms(start)
        status = resp.get("status", 0)
        body = resp.get("body", {})
        resp_error = resp.get("error", "")

        if 200 <= status < 300 and "result" in body:
            results = body["result"]
            count = len(results) if isinstance(results, list) else 1
            logger.info(
                "ServiceNowExecutor: search returned %d incidents",
                count,
            )
            return ActionResult(
                success=True,
                data={
                    "operation": "search_incidents",
                    "query": search_query,
                    "count": count,
                    "records": results,
                },
                duration_ms=elapsed,
            )

        error_msg = resp_error or body.get("error", {}).get("message", "") or f"HTTP {status}"
        logger.error(
            "ServiceNowExecutor: search_incidents failed — %s", error_msg,
        )
        return ActionResult(
            success=False,
            data={"operation": "search_incidents", "query": search_query, "status": status, "response": body},
            error=f"Failed to search incidents: {error_msg}",
            duration_ms=elapsed,
        )

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
