"""
SSE Streamer — Server-Sent Events streaming for Open Design.

Provides real-time streaming of LLM output chunks to Open Design's
iframe, enabling live preview of generated UI as it's being created.

Supports both FastAPI (StreamingResponse) and the legacy stdlib HTTP server.
"""

import json
import time
import uuid
import logging
from typing import Dict, Any, Optional, AsyncIterator, Iterator, Callable, List

from .config import get_open_design_config
from src.core.shared._version import ZENIC_FULL_NAME

logger = logging.getLogger(__name__)


class SSEStreamer:
    """
    Streams LLM output as Server-Sent Events (SSE) for Open Design.

    The SSE format follows the OpenAI streaming spec:
        data: {"id":"zenic-xxx","object":"chat.completion.chunk",
               "choices":[{"delta":{"content":"chunk text"},"index":0}]}

    With additional Open Design event types:
        event: fractal_structure
        data: {...}

        event: fractal_skeleton
        data: {...}

        event: fractal_fill
        data: {...}

        event: artifact
        data: {"identifier":"...","language":"html","code":"..."}
    """

    def __init__(self, request_id: Optional[str] = None):
        self._request_id = request_id or f"zenic-{uuid.uuid4().hex[:8]}"
        self._created = int(time.time())
        self._model = "zenic-agents"
        self._config = get_open_design_config()
        self._chunk_index = 0

    def format_chunk(self, content: str, finish_reason: Optional[str] = None) -> str:
        """
        Format a single SSE chunk following OpenAI streaming spec.

        Args:
            content: Text content for this chunk.
            finish_reason: None for intermediate chunks, "stop" for final.

        Returns:
            Formatted SSE data line: "data: {json}\\n\\n"
        """
        delta: Dict[str, Any] = {"content": content}
        if finish_reason:
            delta["role"] = "assistant"

        chunk = {
            "id": self._request_id,
            "object": "chat.completion.chunk",
            "created": self._created,
            "model": self._model,
            "choices": [{
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }],
        }

        self._chunk_index += 1
        return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    def format_done(self) -> str:
        """Format the SSE [DONE] signal."""
        return "data: [DONE]\n\n"

    def format_event(self, event_type: str, data: Dict[str, Any]) -> str:
        """
        Format a custom SSE event (for fractal phases, artifacts, etc.).

        Args:
            event_type: Event name (e.g., 'fractal_structure', 'artifact').
            data: Event payload as dict.

        Returns:
            Formatted SSE event: "event: type\\ndata: json\\n\\n"
        """
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def format_artifact_event(self, identifier: str, language: str,
                               code: str, title: str = "") -> str:
        """Format an SSE event with an <artifact> tag payload."""
        return self.format_event("artifact", {
            "identifier": identifier,
            "language": language,
            "title": title or f"Generated {language.upper()}",
            "code": code,
        })

    def format_fractal_phase(self, phase: str, data: Dict[str, Any]) -> str:
        """
        Format an SSE event for a FractalGenerator phase.

        Args:
            phase: One of 'structure', 'skeletons', 'fill'.
            data: Phase-specific data (spec, files, progress).

        Returns:
            Formatted SSE event.
        """
        event_name = self._config.fractal_phase_events.get(
            phase, f"fractal_{phase}"
        )
        return self.format_event(event_name, data)

    async def stream_orchestrator_result(
        self,
        result: Dict[str, Any],
        body: Dict[str, Any],
        detection_result: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """
        Stream a complete orchestrator result as SSE chunks.

        Breaks the result into logical chunks for progressive rendering
        in Open Design's iframe. Code content is streamed character-by-character
        for the typing effect; metadata is sent as a single chunk.

        Robustness: If the DAG forced a premature DONE (DAG_TIMEOUT) or
        the result is empty/malformed, we still emit valid SSE chunks so
        Cline doesn't hang waiting for a response that never comes.

        Args:
            result: Orchestrator result dict.
            body: Original request body.
            detection_result: Open Design detection result.

        Yields:
            SSE-formatted strings.
        """
        try:
            # Handle DAG_TIMEOUT or empty results — Cline MUST get a response
            status = result.get("status", "UNKNOWN") if isinstance(result, dict) else "UNKNOWN"
            if status == "DAG_TIMEOUT" or not result:
                logger.warning(
                    "SSE: DAG_TIMEOUT or empty result detected (status=%s), "
                    "sending error chunk to client",
                    status,
                )
                error_msg = (
                    "Pipeline timeout — the DAG exceeded maximum iterations. "
                    "This usually means the model is slow on ARM. "
                    "Please try again — subsequent requests are faster after warm-up."
                )
                yield self.format_chunk(error_msg)
                yield self.format_chunk("", finish_reason="stop")
                yield self.format_done()
                return

            # Extract content from the result (same as build_normal_response)
            content_parts = self._build_content_parts(result)
            full_content = "\n".join(content_parts)

            # If content is still empty after building, send a minimal valid response
            if not full_content or not full_content.strip():
                logger.warning("SSE: Empty content after building parts, sending minimal response")
                full_content = f"{ZENIC_FULL_NAME} - {status} (no output generated)"

            # If artifact wrapping is needed, wrap the content
            if detection_result and (detection_result.get("is_open_design")
                                      or detection_result.get("is_visual_request")):
                from .artifact_builder import ArtifactBuilder
                full_content = ArtifactBuilder.wrap_response_content(
                    full_content, detection_result,
                    language=result.get("ast_analysis", {}).get("language", "html"),
                )

            # Stream content in chunks for progressive rendering
            chunk_size = 4  # Characters per chunk (typing effect)
            for i in range(0, len(full_content), chunk_size):
                chunk_text = full_content[i:i + chunk_size]
                yield self.format_chunk(chunk_text)
                # Small delay for natural typing feel
                if self._config.sse_chunk_delay_s > 0:
                    import asyncio
                    await asyncio.sleep(self._config.sse_chunk_delay_s)

            # Final chunk with finish_reason
            yield self.format_chunk("", finish_reason="stop")
            yield self.format_done()
        except Exception as e:
            logger.error("SSE: stream_orchestrator_result crashed: %s", e, exc_info=True)
            # CRITICAL: Always emit valid SSE even on crash — Cline is waiting
            try:
                yield self.format_chunk(
                    f"[Stream Error: {str(e)[:100]}] The pipeline encountered an error."
                )
                yield self.format_chunk("", finish_reason="stop")
                yield self.format_done()
            except Exception:
                # Absolute last resort — raw SSE DONE signal
                yield "data: [DONE]\n\n"

    def stream_orchestrator_result_sync(
        self,
        result: Dict[str, Any],
        body: Dict[str, Any],
        detection_result: Optional[Dict[str, Any]] = None,
    ) -> Iterator[str]:
        """
        Synchronous version of stream_orchestrator_result.

        Used by the stdlib HTTP server which doesn't support async.
        Robustness: Same DAG_TIMEOUT and empty result handling as async version.
        """
        try:
            # Handle DAG_TIMEOUT or empty results
            status = result.get("status", "UNKNOWN") if isinstance(result, dict) else "UNKNOWN"
            if status == "DAG_TIMEOUT" or not result:
                logger.warning(
                    "SSE (sync): DAG_TIMEOUT or empty result (status=%s)", status,
                )
                error_msg = (
                    "Pipeline timeout — the DAG exceeded maximum iterations. "
                    "Please try again — subsequent requests are faster after warm-up."
                )
                yield self.format_chunk(error_msg)
                yield self.format_chunk("", finish_reason="stop")
                yield self.format_done()
                return

            content_parts = self._build_content_parts(result)
            full_content = "\n".join(content_parts)

            # If content is empty, send minimal response
            if not full_content or not full_content.strip():
                full_content = f"{ZENIC_FULL_NAME} - {status} (no output generated)"

            # Artifact wrapping
            if detection_result and (detection_result.get("is_open_design")
                                      or detection_result.get("is_visual_request")):
                from .artifact_builder import ArtifactBuilder
                full_content = ArtifactBuilder.wrap_response_content(
                    full_content, detection_result,
                    language=result.get("ast_analysis", {}).get("language", "html"),
                )

            # Stream in chunks
            chunk_size = 8  # Larger chunks for sync (no async delay)
            for i in range(0, len(full_content), chunk_size):
                chunk_text = full_content[i:i + chunk_size]
                yield self.format_chunk(chunk_text)

            # Final chunk
            yield self.format_chunk("", finish_reason="stop")
            yield self.format_done()
        except Exception as e:
            logger.error("SSE (sync): stream crashed: %s", e, exc_info=True)
            try:
                yield self.format_chunk(
                    f"[Stream Error: {str(e)[:100]}] The pipeline encountered an error."
                )
                yield self.format_chunk("", finish_reason="stop")
                yield self.format_done()
            except Exception:
                yield "data: [DONE]\n\n"

    def _build_content_parts(self, result: Dict[str, Any]) -> List[str]:
        """Build content parts from orchestrator result (mirrors response_builder)."""
        parts = [f"{ZENIC_FULL_NAME} - {result.get('status', 'UNKNOWN')}"]

        if result.get("explanations"):
            for exp in result["explanations"]:
                parts.append(f"  {exp}")

        if result.get("code"):
            lang = result.get("ast_analysis", {}).get("language", "python")
            parts.append(f"\n```{lang}\n{result['code']}\n```")

        if result.get("warnings"):
            parts.append("\nWarnings:")
            for w in result["warnings"]:
                parts.append(f"  - {w}")

        # Cache hit info (matches build_normal_response)
        if result.get("cache_source"):
            parts.append(
                f"\nCache hit: {result['cache_source']} (hits: {result.get('cache_hits', 0)})"
            )

        # Processing metadata (matches build_normal_response)
        from src.core.shared._version import ZENIC_FULL_NAME as _FN
        from src.core.shared.contracts import HAS_Z3 as _HAS_Z3
        _sname = "Z3" if _HAS_Z3 else "AC-3"
        meta_parts = [
            f"\nTime: {result.get('processing_time_ms', 0)}ms",
            f"Route: {result.get('route', 'N/A')}",
            f"Hash: {result.get('hash', 'N/A')}",
            f"Solver({_sname}): {result.get('solver_status', 'N/A')}",
        ]
        parts.append(" | ".join(meta_parts))

        return parts


def create_sse_response(streamer: SSEStreamer,
                         result: Dict[str, Any],
                         body: Dict[str, Any],
                         detection_result: Optional[Dict[str, Any]] = None):
    """
    Create a FastAPI StreamingResponse for SSE.

    Args:
        streamer: SSEStreamer instance.
        result: Orchestrator result.
        body: Request body.
        detection_result: Open Design detection result.

    Returns:
        FastAPI StreamingResponse with SSE content type.
    """
    try:
        from fastapi.responses import StreamingResponse
    except ImportError:
        raise ImportError(
            "FastAPI is required for SSE streaming. "
            "Install with: pip install fastapi uvicorn"
        )

    return StreamingResponse(
        streamer.stream_orchestrator_result(result, body, detection_result),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )
