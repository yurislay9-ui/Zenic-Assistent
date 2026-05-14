"""
Chat completions endpoint — OpenAI-compatible /v1/chat/completions.

This is the primary AI endpoint, supporting both standard JSON responses
and SSE streaming (basic + Open Design).
"""

from typing import Any, Optional

from src.server.fastapi_parts._imports import (
    time,
    uuid,
    asyncio,
    logging,
    logger,
    AuthContext,
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_artifact_response,
    CircuitOpenError,
    _ORCH_RETRY,
    _orch_breaker,
    with_retry,
    _OPEN_DESIGN_AVAILABLE,
)
from src.server.fastapi_parts._helpers import (
    _basic_sse_generator,
    _run_orchestrator,
    _extract_user_message,
)


def register_chat_routes(
    app: Any,
    *,
    orchestrator: Any,
    governor: Optional[Any],
) -> None:
    """Register chat/completions route on *app*."""

    from fastapi import Request, HTTPException
    from fastapi.responses import JSONResponse

    # ── /v1/chat/completions ────────────────────────────────
    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        """OpenAI-compatible chat completions endpoint with SSE streaming for Open Design."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        messages = body.get("messages", [])
        if not messages:
            raise HTTPException(status_code=400, detail="No messages provided")

        user_msg = _extract_user_message(body)
        if not user_msg:
            raise HTTPException(status_code=400, detail="No user message found")

        # ── Open Design Detection ──
        detection_result = None
        if _OPEN_DESIGN_AVAILABLE:
            try:
                from src.server.fastapi_parts._imports import OpenDesignDetector

                headers_dict = {k.lower(): v for k, v in request.headers.items()}
                detection_result = OpenDesignDetector.detect(
                    messages=messages, headers=headers_dict, body=body,
                )
                if detection_result.get("is_open_design") or detection_result.get("is_visual_request"):
                    logger.info(
                        "OpenDesign: detected request (bypass=%s, DS=%s, signals=%s)",
                        detection_result.get("bypass_solver"),
                        detection_result.get("has_design_system"),
                        detection_result.get("detection_signals"),
                    )
            except Exception as e:
                logger.warning("OpenDesign detection failed (skipping): %s", e)
                detection_result = None

        # Execute with retry + circuit breaker
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                _orch_breaker.call,
                with_retry,
                _run_orchestrator,
                _ORCH_RETRY,
                orchestrator,
                user_msg,
            )
        except CircuitOpenError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Service temporarily unavailable: {e}",
            )
        except Exception as e:
            logger.error("Orchestrator error: %s", e, exc_info=True)
            return JSONResponse(
                status_code=500,
                content=build_error_response(str(e)),
            )

        # Defensive: ensure result is never None
        if result is None:
            logger.error("chat_completions: orchestrator returned None — building error response")
            result = {"status": "ERROR", "code": "", "error": "Orchestrator returned empty result"}

        # ── SSE Streaming ──
        if body.get("stream", False):
            if (
                _OPEN_DESIGN_AVAILABLE
                and detection_result
                and (
                    detection_result.get("is_open_design")
                    or detection_result.get("is_visual_request")
                )
            ):
                # Open Design: full SSE with fractal phases and artifact events
                try:
                    from src.server.fastapi_parts._imports import SSEStreamer, create_sse_response

                    streamer = SSEStreamer()
                    return create_sse_response(streamer, result, body, detection_result)
                except Exception as e:
                    logger.warning("OpenDesign: SSE streaming failed, falling back to basic SSE: %s", e)
            # General Cline or Open Design fallback: basic SSE streaming
            try:
                from fastapi.responses import StreamingResponse

                return StreamingResponse(
                    _basic_sse_generator(body, result),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            except Exception as e:
                logger.warning("SSE streaming failed, falling back to JSON: %s", e)

        # Standard JSON response
        if result.get("partial_reasoning"):
            return build_partial_reasoning_response(body, result, user_msg)

        # Open Design: artifact-wrapped response for visual requests (non-streaming)
        if detection_result and (
            detection_result.get("is_open_design") or detection_result.get("is_visual_request")
        ):
            return build_artifact_response(body, result, user_msg, governor=governor)

        # Detect fallback-only responses (all LLM calls timed out or failed)
        mini_ai_stats = result.get("mini_ai_stats", {})
        fallback_rate = mini_ai_stats.get("fallback_rate", 0.0)
        total_calls = mini_ai_stats.get("total_calls", 0)
        if total_calls > 0 and fallback_rate >= 1.0:
            logger.warning(
                "chat_completions: 100%% fallback rate (%d calls) — model not responding",
                total_calls,
            )
            return JSONResponse(
                status_code=503,
                content=build_error_response(
                    "Model inference timed out — the AI model is not responding in time. "
                    "This is common on first request after startup (warm-up). "
                    "Please try again — subsequent requests will be faster."
                ),
            )

        return build_normal_response(body, result, user_msg, governor=governor)
