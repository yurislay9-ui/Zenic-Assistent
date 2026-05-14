"""
Dispatch endpoint mixin for ZenicHTTPHandler.

Provides the /v1/dispatch endpoint that bridges the stdlib HTTP server
to the ActionExecutor registry, allowing external clients to invoke
any registered executor (email, http, database, file, etc.) via a
single JSON POST.

Extracted from _post_mixin.py to keep each file under 400 lines.
"""

from ._imports import (
    logger, json, _run_async,
    _get_executor_registry,
    _EXECUTOR_REGISTRY_AVAILABLE,
)


class DispatchMixin:
    """Executor dispatch endpoint for ZenicHTTPHandler.

    Handles POST /v1/dispatch — dispatches an action to the
    ``ExecutorRegistry`` and returns the ``ActionResult`` as JSON.
    """

    def _handle_dispatch(self):
        """POST /v1/dispatch — Execute an action via the executor registry.

        Expected JSON body::

            {
                "action_type": "email",
                "config": {...},
                "context": {...}   // optional
            }

        Returns the ``ActionResult`` serialised as JSON.
        """
        # ── Availability gate ──
        if not _EXECUTOR_REGISTRY_AVAILABLE:
            self._send_json(
                {"error": "Executor registry not available"},
                status=503,
            )
            return

        # ── Parse body ──
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json(
                {"error": f"Invalid JSON: {e}"},
                status=400,
            )
            return

        # ── Validate required fields ──
        action_type: str = data.get("action_type", "")
        if not action_type:
            self._send_json(
                {"error": "Missing 'action_type' field"},
                status=400,
            )
            return

        config: dict = data.get("config", {})
        if not isinstance(config, dict):
            self._send_json(
                {"error": "'config' must be a JSON object"},
                status=400,
            )
            return

        context: dict = data.get("context", {})
        if not isinstance(context, dict):
            self._send_json(
                {"error": "'context' must be a JSON object"},
                status=400,
            )
            return

        # ── Execute via registry ──
        try:
            registry = _get_executor_registry()
            result = _run_async(
                registry.execute_action(action_type, config, context),
            )
            # ActionResult.to_dict() gives a clean serialisable mapping
            response = result.to_dict() if hasattr(result, "to_dict") else {
                "success": getattr(result, "success", False),
                "data": getattr(result, "data", {}),
                "error": getattr(result, "error", ""),
                "duration_ms": getattr(result, "duration_ms", 0.0),
            }
            self._send_json(response)
        except Exception as e:
            logger.error("Dispatch error for '%s': %s", action_type, e, exc_info=True)
            self._send_json(
                {"error": f"Executor dispatch failed: {e}"},
                status=500,
            )
