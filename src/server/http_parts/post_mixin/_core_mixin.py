"""PostMixin - Core methods."""

import json
import logging
import time

from ._shared import (
    logger,
    _run_async,
    _REQUEST_TIMEOUT,
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
    build_artifact_response,
    _extract_msg_text,
    _OPEN_DESIGN_AVAILABLE,
)

# Conditional imports for Open Design
if _OPEN_DESIGN_AVAILABLE:
    from ._shared import OpenDesignDetector, SSEStreamer


class PostMixinCoreMixin:
    """Core methods."""

    def do_POST(self):
        if self.path == '/v1/chat/completions':
            self._handle_chat_completions()
        elif self.path == '/v1/generate/app':
            self._handle_generate_app()
        elif self.path == '/v1/generate/automation':
            self._handle_generate_automation()
        elif self.path == '/v1/generate/niche':
            self._handle_generate_niche()
        elif self.path == '/v1/design/schema':
            self._handle_design_schema()
        elif self.path == '/v1/think':
            self._handle_think()
        elif self.path == '/v1/reason':
            self._handle_reason()
        elif self.path == '/v1/chain/validate':
            self._handle_chain_validate()
        elif self.path == '/v1/chain/execute':
            self._handle_chain_execute()
        elif self.path == '/v1/system/context-index':
            self._handle_context_index_post()
        elif self.path == '/v1/system/auto-evolve/trigger':
            self._handle_auto_evolve_trigger()
        elif self.path == '/v1/dna/validate':
            self._handle_dna_validate()
        elif self.path == '/v1/dna/polish':
            self._handle_dna_polish()
        elif self.path == '/v1/dispatch':
            self._handle_dispatch()
        else:
            self._send_json({"error": "Not found"}, status=404)
    def _handle_chat_completions(self):
        """Procesa peticion /v1/chat/completions con rate limiting, governor, y SSE streaming."""
        client_ip = self.client_address[0]
        if self.rate_limiter and not self.rate_limiter.acquire(client_ip):
            self._send_json({
                "error": {"message": "Rate limit exceeded. Slow down.",
                          "type": "rate_limit_exceeded"}
            }, status=429)
            return

        gov = self.governor
        if gov:
            gov.pre_request()

        # Wrap everything in try/finally so rate_limiter.release() and
        # gov.post_request() are ALWAYS called exactly once, even on
        # early returns (RAM critical) or crashes.
        try:
            if gov and gov.is_ram_critical():
                self._send_json(build_overloaded_response(), status=503)
                return  # finally block will release resources
            try:
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length).decode('utf-8')
                data = json.loads(body)
            except (json.JSONDecodeError, ValueError) as e:
                self._send_json({
                    "error": {"message": f"Invalid JSON: {str(e)}",
                              "type": "invalid_request_error"}
                }, status=400)
                return

            messages = data.get("messages", [])
            if not messages:
                self._send_json({
                    "error": {"message": "No messages provided",
                              "type": "invalid_request_error"}
                }, status=400)
                return

            # Extract user message — content can be string or list (OpenAI multimodal)
            user_msg = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    user_msg = _extract_msg_text(msg.get("content", ""))
                    break

            if not user_msg:
                self._send_json({
                    "error": {"message": "No user message found",
                              "type": "invalid_request_error"}
                }, status=400)
                return

            # ── Open Design Detection ──
            detection_result = None
            if _OPEN_DESIGN_AVAILABLE:
                try:
                    headers_dict = {
                        k.lower(): v for k, v in self.headers.items()
                    }
                    detection_result = OpenDesignDetector.detect(
                        messages=messages, headers=headers_dict, body=data,
                    )
                except Exception as e:
                    logger.warning("OpenDesign detection failed (skipping): %s", e)
                    detection_result = None

            result = _run_async(self.orchestrator.execute(user_msg))

            # ── Defensive: ensure result is never None/empty ──
            # If the orchestrator returns None (e.g. exception swallowed),
            # Cline would receive an empty HTTP body → parse error → crash
            if result is None:
                logger.error("chat_completions: orchestrator returned None")
                self._send_json(build_error_response("Orchestrator returned empty result"), status=500)
                return

            # ── SSE Streaming ──
            # OpenAI spec: when stream=true, client expects SSE format.
            # For Open Design requests, use full SSEStreamer with fractal phases.
            # For general Cline requests with stream=true, use basic SSE streaming.
            if data.get("stream", False):
                if (_OPEN_DESIGN_AVAILABLE
                        and detection_result
                        and (detection_result.get("is_open_design")
                             or detection_result.get("is_visual_request"))):
                    # Open Design: full SSE with fractal phases and artifact events
                    self._send_sse_stream(result, data, detection_result)
                    return
                else:
                    # General Cline request with stream=true: basic SSE streaming
                    self._send_sse_basic(result, data)
                    return

            # Standard JSON response
            if result.get("partial_reasoning"):
                response = build_partial_reasoning_response(data, result, user_msg)
                self._send_json(response)
                return

            # Open Design: Use artifact-wrapped response for visual requests (non-streaming)
            if (detection_result
                    and (detection_result.get("is_open_design")
                         or detection_result.get("is_visual_request"))):
                response = build_artifact_response(data, result, user_msg, governor=gov)
                self._send_json(response)
                return

            response = build_normal_response(data, result, user_msg, governor=gov)
            http_status = 500 if result.get("status") in ("ERROR", "ROLLBACK", "DAG_TIMEOUT") else 200
            self._send_json(response, status=http_status)
        except TimeoutError:
            logger.error(
                "Request TIMEOUT after %ds — orchestrator took too long. "
                "Increase ZENIC_REQUEST_TIMEOUT or check model loading.",
                _REQUEST_TIMEOUT,
            )
            self._send_json({
                "error": {
                    "message": f"Request timed out after {_REQUEST_TIMEOUT}s. "
                               "The model may still be loading. Try again in a moment.",
                    "type": "timeout_error",
                }
            }, status=504)
        except Exception as e:
            logger.error("Error processing request: %s", e, exc_info=True)
            self._send_json(build_error_response(str(e)), status=500)
        finally:
            if gov:
                gov.post_request()
            if self.rate_limiter:
                self.rate_limiter.release()
    def _send_sse_basic(self, result, data):
        """Send orchestrator result as basic SSE stream for general Cline requests.

        Follows OpenAI streaming spec: each chunk is a chat.completion.chunk object.
        This is used when Cline sends stream=true but is NOT an Open Design request.
        """
        import uuid
        request_id = f"zenic-{uuid.uuid4().hex[:8]}"
        created = int(time.time()) if hasattr(time, 'time') else 0
        model = data.get("model", "zenic-agents")

        # Build the full content first (reuse build_normal_response logic)
        response = build_normal_response(data, result, "")
        content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

        if not content:
            content = f"[No output generated - status: {result.get('status', 'UNKNOWN')}]"

        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('X-Accel-Buffering', 'no')
            self._set_cors_headers()
            self.end_headers()

            # Stream content in chunks following OpenAI format
            chunk_size = 8
            for i in range(0, len(content), chunk_size):
                chunk_text = content[i:i + chunk_size]
                sse_chunk = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": chunk_text},
                        "finish_reason": None,
                    }],
                }
                self.wfile.write(f"data: {json.dumps(sse_chunk, ensure_ascii=False)}\n\n".encode('utf-8'))
                self.wfile.flush()

            # Final chunk with finish_reason="stop"
            final_chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"role": "assistant", "content": ""},
                    "finish_reason": "stop",
                }],
            }
            self.wfile.write(f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n".encode('utf-8'))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception as e:
            logger.error("SSE basic streaming error: %s", e, exc_info=True)
            # Try to send error as final SSE chunk
            try:
                error_chunk = {
                    "id": request_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": f"\n[Stream Error: {str(e)[:100]}]"},
                        "finish_reason": "stop",
                    }],
                }
                self.wfile.write(f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n".encode('utf-8'))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except Exception:
                pass
    def _send_sse_stream(self, result, data, detection_result):
        """Send orchestrator result as SSE stream for Open Design."""
        # Create streamer BEFORE sending headers so we can fall back to JSON on error
        try:
            streamer = SSEStreamer()
        except Exception as e:
            logger.error("SSE: Failed to create streamer: %s", e, exc_info=True)
            self._send_json(build_error_response(f"Streaming unavailable: {e}"), status=500)
            return
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('X-Accel-Buffering', 'no')
            # CORS headers for Open Design
            self._set_cors_headers()
            self.end_headers()

            # Stream the result as SSE chunks
            for chunk in streamer.stream_orchestrator_result_sync(
                result, data, detection_result
            ):
                self.wfile.write(chunk.encode('utf-8'))
                self.wfile.flush()
        except Exception as e:
            logger.error("SSE streaming error: %s", e, exc_info=True)
            # Try to send error as SSE event
            try:
                error_chunk = streamer.format_chunk(
                    f"\n[Stream Error: {str(e)}]", finish_reason="stop"
                )
                self.wfile.write(error_chunk.encode('utf-8'))
                self.wfile.write(streamer.format_done().encode('utf-8'))
                self.wfile.flush()
            except Exception:
                pass
    def _handle_generate_app(self):
        """POST /v1/generate/app - Generar app completa."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return
        description = data.get("description", "")
        if not description:
            self._send_json({"error": "Missing 'description' field"}, status=400)
            return
        project_name = data.get("project_name", "")
        output_dir = data.get("output_dir", "")
        try:
            result = _run_async(self.orchestrator.generate_app(description, project_name, output_dir))
            if result is None:
                result = {"error": "Orchestrator returned empty result"}
            self._send_json(result)
        except Exception as e:
            logger.error(f"App generation error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)
    def _handle_generate_automation(self):
        """POST /v1/generate/automation - Generar automatizacion."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return
        description = data.get("description", "")
        if not description:
            self._send_json({"error": "Missing 'description' field"}, status=400)
            return
        output_dir = data.get("output_dir", "")
        try:
            result = _run_async(self.orchestrator.generate_automation(description, output_dir))
            if result is None:
                result = {"error": "Orchestrator returned empty result"}
            self._send_json(result)
        except Exception as e:
            logger.error(f"Automation generation error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)
    def _handle_generate_niche(self):
        """POST /v1/generate/niche - Generar app desde nicho predefinido."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": f"Invalid JSON: {e}"}, status=400)
            return
        niche_name = data.get("niche", "")
        if not niche_name:
            description = data.get("description", "")
            if not description:
                self._send_json({"error": "Missing 'niche' or 'description' field"}, status=400)
                return
            try:
                from src.core.template_engine import TemplateEngine
                engine = TemplateEngine()
                results = engine.search_niches(description, limit=1)
                if results:
                    niche_name = results[0].get("name", "")
                else:
                    self._send_json({"error": f"No niche found matching: {description}"}, status=404)
                    return
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
                return
        output_dir = data.get("output_dir", "")
        try:
            from src.core.template_engine import TemplateEngine
            engine = TemplateEngine()
            plan = engine.get_niche_plan(niche_name)
            if not plan:
                self._send_json({"error": f"Niche '{niche_name}' not found"}, status=404)
                return
            files = engine.render_niche(niche_name)
            self._send_json({
                "niche": niche_name, "files_generated": len(files),
                "files": list(files.keys()), "entities": len(plan.entities),
                "blocks": plan.blocks,
            })
        except Exception as e:
            logger.error(f"Niche generation error: {e}", exc_info=True)
            self._send_json({"error": str(e)}, status=500)
