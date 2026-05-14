"""
Executor / dispatch / distributed orchestration endpoints.

Phase 3: /v1/actions/*, /v1/executors, /v1/audit
Phase 4: /v1/cluster/*, /v1/tasks/*, /v1/saga/*
"""

from typing import Any, Optional

from src.server.fastapi_parts._imports import (
    time,
    uuid,
    logging,
    logger,
    AuthContext,
)


def register_executor_routes(
    app: Any,
    *,
    auth_service: Optional[Any],
    require_auth_dep: Any,
) -> None:
    """Register executor, dispatch, and distributed-orchestration routes on *app*."""

    from fastapi import Request, HTTPException, Depends
    from fastapi.responses import JSONResponse

    # ════════════════════════════════════════════════════════
    #  Phase 3: Executor Dispatch Endpoints
    # ════════════════════════════════════════════════════════

    @app.post("/v1/actions/dispatch")
    async def dispatch_action(request: Request):
        """Dispatch an action through the Safety Gate → Executor → Audit pipeline."""
        from src.core.executors.dispatch_action import ActionDispatcher, DispatchRequest
        from src.core.executors.safety_gate import SafetyVerdict

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        action_type = body.get("action_type", "")
        config = body.get("config", {})
        context = body.get("context", {})

        if not action_type:
            raise HTTPException(status_code=400, detail="Missing 'action_type' field")

        auth_ctx = getattr(request.state, "auth_ctx", None)
        dispatch_req = DispatchRequest(
            action_type=action_type,
            config=config,
            context=context,
            user_id=auth_ctx.user_id if auth_ctx else "",
            tenant_id=auth_ctx.tenant_id if auth_ctx else "",
            session_id=getattr(request.state, "session_id", ""),
            request_id=str(uuid.uuid4()),
        )

        dispatcher = ActionDispatcher()
        result = await dispatcher.dispatch(dispatch_req)

        if result.safety_verdict == SafetyVerdict.DENY:
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Action denied by safety gate",
                    "reason": result.safety_result.reason if result.safety_result else "",
                    "action_id": result.action_id,
                },
            )
        if result.safety_verdict == SafetyVerdict.RATE_LIMITED:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limited",
                    "reason": result.safety_result.reason if result.safety_result else "",
                    "action_id": result.action_id,
                },
            )
        if result.safety_verdict in (SafetyVerdict.CONFIRM, SafetyVerdict.APPROVE):
            return JSONResponse(
                status_code=202,
                content={
                    "status": "pending",
                    "safety_verdict": result.safety_verdict.value,
                    "action_id": result.action_id,
                    "reason": result.safety_result.reason if result.safety_result else "",
                },
            )

        status_code = 200 if result.success else 422
        return JSONResponse(
            status_code=status_code,
            content={
                "action_id": result.action_id,
                "success": result.success,
                "safety_verdict": result.safety_verdict.value,
                "duration_ms": result.total_duration_ms,
                "executor_result": result.executor_result.to_dict() if result.executor_result else None,
                "pipeline_stages": result.pipeline_stages,
            },
        )

    @app.post("/v1/actions/confirm/{action_id}")
    async def confirm_action(action_id: str):
        """Confirm a pending action that requires user confirmation."""
        from src.core.executors.dispatch_action import get_default_dispatcher

        dispatcher = get_default_dispatcher()
        result = dispatcher.confirm_action(action_id)
        if result is None:
            return {"status": "confirmed", "action_id": action_id}
        return {"status": "not_pending", "action_id": action_id}

    @app.post("/v1/actions/approve/{action_id}")
    async def approve_action(action_id: str, request: Request):
        """Approve a pending action that requires role approval."""
        from src.core.executors.dispatch_action import get_default_dispatcher

        try:
            body = await request.json()
        except Exception:
            body = {}
        approver_role = body.get("approver_role", "admin")
        dispatcher = get_default_dispatcher()
        result = dispatcher.approve_action(action_id, approver_role)
        if result is None:
            return {"status": "approved", "action_id": action_id, "approver_role": approver_role}
        return {"status": "not_pending", "action_id": action_id}

    @app.get("/v1/actions/pending")
    async def get_pending_actions():
        """Get all actions pending confirmation or approval."""
        from src.core.executors.dispatch_action import get_default_dispatcher

        dispatcher = get_default_dispatcher()
        return {
            "confirmations": dispatcher.get_pending_confirmations(),
            "approvals": dispatcher.get_pending_approvals(),
        }

    @app.get("/v1/executors")
    async def list_executors():
        """List all registered executors and their capabilities."""
        from src.core.executors.base import get_default_registry

        registry = get_default_registry()
        return registry.stats

    @app.get("/v1/audit")
    async def query_audit(request: Request):
        """Query executor audit trail."""
        from src.core.executors.audit_logger import get_default_audit_logger, AuditQuery

        audit = get_default_audit_logger()
        params = dict(request.query_params)
        q = AuditQuery(
            action_type=params.get("action_type"),
            user_id=params.get("user_id"),
            tenant_id=params.get("tenant_id"),
            success=params.get("success", "").lower() == "true" if params.get("success") else None,
            limit=int(params.get("limit", "100")),
            offset=int(params.get("offset", "0")),
        )
        entries = audit.query(q)
        return {
            "entries": [
                {
                    "entry_id": e.entry_id,
                    "action_type": e.action_type,
                    "operation": e.operation,
                    "verdict": e.verdict,
                    "success": e.success,
                    "duration_ms": e.duration_ms,
                    "risk_score": e.risk_score,
                    "merkle_hash": e.merkle_hash[:16],
                    "timestamp": e.timestamp,
                }
                for e in entries
            ],
            "count": len(entries),
        }

    # ════════════════════════════════════════════════════════
    #  Phase 4: Distributed Orchestration Endpoints
    # ════════════════════════════════════════════════════════

    @app.get("/v1/cluster/nodes")
    async def cluster_nodes(auth_ctx: AuthContext = Depends(require_auth_dep)):
        """List active nodes in the distributed cluster."""
        if not auth_ctx.has_role("manager"):
            raise HTTPException(status_code=403, detail="Manager role required")
        try:
            from src.core.distributed import ClusterTopology

            backend = getattr(app.state, "coordination_backend", None)
            if backend is None:
                return {"nodes": [], "total": 0, "distributed": False}
            topology = ClusterTopology(backend=backend)
            nodes = await topology.list_active_nodes()
            return {
                "nodes": [
                    {
                        "node_id": n.node_id,
                        "hostname": n.hostname,
                        "ip_address": n.ip_address,
                        "capabilities": n.capabilities,
                        "state": n.state.value,
                        "last_heartbeat": n.last_heartbeat,
                    }
                    for n in nodes
                ],
                "total": len(nodes),
                "distributed": True,
            }
        except Exception as e:
            logger.error("Cluster nodes error: %s", e)
            return {"nodes": [], "total": 0, "error": str(e)}

    @app.get("/v1/cluster/status")
    async def cluster_status(auth_ctx: AuthContext = Depends(require_auth_dep)):
        """Get cluster-wide distributed orchestration status."""
        if not auth_ctx.has_role("manager"):
            raise HTTPException(status_code=403, detail="Manager role required")
        try:
            backend = getattr(app.state, "coordination_backend", None)
            if backend is None:
                return {
                    "distributed": False,
                    "backend_type": "none",
                    "message": "Coordination backend not configured",
                }
            health = await backend.health_check()
            return {
                "distributed": True,
                "backend_type": type(backend).__name__,
                "health": health,
                "node_id": backend.node_id,
            }
        except Exception as e:
            logger.error("Cluster status error: %s", e)
            return {"distributed": False, "error": str(e)}

    @app.post("/v1/tasks/enqueue")
    async def enqueue_task(request: Request, auth_ctx: AuthContext = Depends(require_auth_dep)):
        """Enqueue a task to the distributed task queue."""
        if not auth_ctx.has_role("user"):
            raise HTTPException(status_code=403, detail="User role required")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        queue_name = body.get("queue_name", "default")
        task_type = body.get("task_type", "generic")
        payload = body.get("payload", {})
        priority = body.get("priority", 5)
        tenant_id = body.get("tenant_id")
        delay_seconds = body.get("delay_seconds")

        try:
            from src.core.distributed import DistributedTaskQueue, TaskMessage

            backend = getattr(app.state, "coordination_backend", None)
            if backend is None:
                raise HTTPException(status_code=503, detail="Distributed task queue not available")
            task_queue = getattr(app.state, "task_queue", None)
            if task_queue is None:
                raise HTTPException(status_code=503, detail="Task queue not initialized")

            delay_until = None
            if delay_seconds and delay_seconds > 0:
                delay_until = time.time() + delay_seconds

            msg = TaskMessage(
                queue_name=queue_name,
                task_type=task_type,
                payload=payload,
                priority=priority,
                delay_until=delay_until,
                tenant_id=tenant_id,
            )
            task_id = await task_queue.enqueue(msg)
            return {"task_id": task_id, "status": "enqueued", "queue": queue_name}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Task enqueue error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/tasks/{task_id}/status")
    async def task_status(task_id: str, auth_ctx: AuthContext = Depends(require_auth_dep)):
        """Get the status of a distributed task."""
        if not auth_ctx.has_role("user"):
            raise HTTPException(status_code=403, detail="User role required")
        try:
            backend = getattr(app.state, "coordination_backend", None)
            if backend is None:
                raise HTTPException(status_code=503, detail="Backend not available")
            saga = await backend.get_saga(task_id)
            if saga:
                return {
                    "task_id": task_id,
                    "type": "saga",
                    "status": saga.get("status"),
                    "name": saga.get("name"),
                    "steps": len(saga.get("steps", [])),
                }
            return {"task_id": task_id, "status": "unknown"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Task status error: %s", e)
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/v1/saga/start")
    async def start_saga(request: Request, auth_ctx: AuthContext = Depends(require_auth_dep)):
        """Start a new distributed SAGA."""
        if not auth_ctx.has_role("manager"):
            raise HTTPException(status_code=403, detail="Manager role required")
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        name = body.get("name", "")
        steps = body.get("steps", [])
        initial_context = body.get("context", {})

        if not name:
            raise HTTPException(status_code=400, detail="Missing 'name' field")
        if not steps:
            raise HTTPException(status_code=400, detail="Missing 'steps' field")

        try:
            from src.core.distributed import DistributedSagaCoordinator, DistributedSagaStep

            backend = getattr(app.state, "coordination_backend", None)
            task_queue = getattr(app.state, "task_queue", None)
            if backend is None or task_queue is None:
                raise HTTPException(status_code=503, detail="Distributed orchestration not available")

            saga_coordinator = DistributedSagaCoordinator(backend=backend, task_queue=task_queue)
            saga_steps = [
                DistributedSagaStep(
                    name=step.get("name", f"step-{i}"),
                    action_task_type=step.get("action_task_type", f"saga_step_{step.get('name', i)}"),
                    compensation_task_type=step.get("compensation_task_type"),
                    timeout=step.get("timeout"),
                    priority=step.get("priority", 5),
                )
                for i, step in enumerate(steps)
            ]

            tenant_id = getattr(
                getattr(request.state, "tenant_ctx", None),
                "effective_tenant_id",
                None,
            )
            saga_id = await saga_coordinator.start_saga(
                name=name,
                steps=saga_steps,
                initial_context=initial_context,
                tenant_id=tenant_id,
            )
            return {"saga_id": saga_id, "name": name, "steps": len(saga_steps), "status": "RUNNING"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Saga start error: %s", e, exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/v1/saga/{saga_id}")
    async def get_saga_status(saga_id: str, auth_ctx: AuthContext = Depends(require_auth_dep)):
        """Get the status of a distributed SAGA."""
        if not auth_ctx.has_role("user"):
            raise HTTPException(status_code=403, detail="User role required")
        try:
            backend = getattr(app.state, "coordination_backend", None)
            if backend is None:
                raise HTTPException(status_code=503, detail="Backend not available")
            saga = await backend.get_saga(saga_id)
            if saga is None:
                raise HTTPException(status_code=404, detail="Saga not found")
            return saga
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Saga status error: %s", e)
            raise HTTPException(status_code=500, detail=str(e))
