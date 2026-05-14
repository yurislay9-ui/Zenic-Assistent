"""
Helper functions and utilities shared across FastAPI route modules.

Includes SSE streaming, orchestrator execution, tenant-context building,
and user-message extraction helpers.
"""

from typing import Any, Dict, List, Optional

from src.server.fastapi_parts._imports import (
    json,
    time,
    uuid,
    asyncio,
    logging,
    logger,
    build_normal_response,
    AuthContext,
    TenantContext,
    PLAN_DEFINITIONS,
    _orch_breaker,
    _ORCH_RETRY,
    with_retry,
    resolve_auth,
    require_auth,
)


# ────────────────────────────────────────────────────────────
#  SSE streaming generator
# ────────────────────────────────────────────────────────────

async def _basic_sse_generator(body: Dict[str, Any], result: Dict[str, Any]):
    """Async generator for basic SSE streaming of orchestrator results.

    Follows OpenAI streaming spec: each chunk is a chat.completion.chunk object.
    Used when Cline sends stream=true but is NOT an Open Design request.
    """
    request_id = f"zenic-{uuid.uuid4().hex[:8]}"
    created = int(time.time())
    model = body.get("model", "zenic-agents")

    # Build full content using the same logic as build_normal_response
    user_msg = _extract_user_message(body)

    response = build_normal_response(body, result, user_msg)
    content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

    if not content:
        content = f"[No output generated - status: {result.get('status', 'UNKNOWN')}]"

    try:
        # Stream content in chunks
        chunk_size = 8
        for i in range(0, len(content), chunk_size):
            chunk_text = content[i : i + chunk_size]
            sse_chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": chunk_text},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(sse_chunk, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)  # Yield control to event loop

        # Final chunk with finish_reason="stop"
        final_chunk = {
            "id": request_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "content": ""},
                    "finish_reason": "stop",
                }
            ],
        }
        yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.error("SSE generator crashed: %s", e, exc_info=True)
        try:
            error_chunk = {
                "id": request_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": f"\n[Stream Error: {str(e)[:100]}]"},
                        "finish_reason": "stop",
                    }
                ],
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            yield "data: [DONE]\n\n"


# ────────────────────────────────────────────────────────────
#  Orchestrator execution (for retry / circuit-breaker)
# ────────────────────────────────────────────────────────────

def _run_orchestrator(orchestrator: Any, user_msg: str) -> Dict[str, Any]:
    """Synchronous orchestrator execution (for retry/circuit breaker).

    Handles both sync and async execute() methods.
    Called from run_in_executor so it runs in a worker thread, NOT the event loop.
    """
    import asyncio as _asyncio

    result = orchestrator.execute(user_msg)
    # Handle coroutine — since we're in a worker thread, asyncio.run() is safe
    if _asyncio.iscoroutine(result):
        return _asyncio.run(result)
    return result


# ────────────────────────────────────────────────────────────
#  User-message extraction
# ────────────────────────────────────────────────────────────

def _extract_user_message(body: Dict[str, Any]) -> str:
    """Extract the last user message from an OpenAI-compatible request body.

    Handles both plain string content and multimodal (list-of-parts) content.
    """
    user_msg = ""
    messages = body.get("messages", [])
    for msg in reversed(messages):
        if msg.get("role") == "user":
            raw = msg.get("content", "")
            if isinstance(raw, list):
                user_msg = " ".join(
                    p.get("text", "")
                    if isinstance(p, dict) and p.get("type") == "text"
                    else (p if isinstance(p, str) else "")
                    for p in raw
                )
            else:
                user_msg = str(raw)
            break
    return user_msg


# ────────────────────────────────────────────────────────────
#  Tenant-context builder
# ────────────────────────────────────────────────────────────

def _build_tenant_context(
    auth_ctx: Optional[AuthContext],
    auth_service: Any,
) -> TenantContext:
    """Build a TenantContext from an AuthContext, resolving plan/quotas/features."""
    if auth_ctx is None or not auth_ctx.tenant_id:
        return TenantContext.anonymous()

    # Resolve tenant plan and quotas
    tenant = auth_service.get_tenant(auth_ctx.tenant_id) if auth_service else None
    plan = tenant.get("plan", "free") if tenant else "free"
    quotas = PLAN_DEFINITIONS.get(plan, PLAN_DEFINITIONS["free"])
    features = quotas.get("features", [])

    return TenantContext.from_auth_context(
        auth_ctx=auth_ctx,
        plan=plan,
        quotas=quotas,
        features=features if isinstance(features, list) else [],
    )


# ────────────────────────────────────────────────────────────
#  Auth dependency factories
# ────────────────────────────────────────────────────────────

def make_auth_dependencies(auth_service: Optional[Any]):
    """Return ``(get_auth_context, require_auth_dep)`` callables for FastAPI Depends()."""

    from fastapi import HTTPException, Request

    async def get_auth_context(request: Request) -> Optional[AuthContext]:
        """Resolve auth from request headers. Returns None when auth is disabled."""
        if auth_service is None:
            return None
        authorization = request.headers.get("Authorization", "")
        api_key = request.headers.get("X-API-Key", "")
        ctx = resolve_auth(auth_service, authorization or None, api_key or None)
        return ctx

    async def require_auth_dep(request: Request) -> AuthContext:
        """Require valid authentication — raises 401 if missing/invalid."""
        if auth_service is None:
            raise HTTPException(status_code=401, detail="Authentication not configured")
        authorization = request.headers.get("Authorization", "")
        api_key = request.headers.get("X-API-Key", "")
        result = require_auth(auth_service, authorization or None, api_key or None)
        if "error" in result:
            raise HTTPException(
                status_code=result.get("status", 401), detail=result["error"],
            )
        return result["auth"]

    return get_auth_context, require_auth_dep
