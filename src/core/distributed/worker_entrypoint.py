"""
ZENIC-AGENTS - Distributed Worker Entrypoint

Standalone entry point for distributed worker processes.
Started by docker-compose with: python -m src.core.distributed.worker_entrypoint

Reads configuration from environment variables and starts a
DistributedWorker that connects to the coordination backend
and processes tasks from the configured queues.
"""

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .worker import DistributedWorker
import os
import signal
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("worker-entrypoint")


def main() -> None:
    """Start the distributed worker process."""
    from src.core.distributed import (
        BackendConfig,
        BackendType,
        CoordinationBackend,
        DistributedTaskQueue,
        DistributedWorker,
        WorkerConfig,
    )
    from src.core.distributed.topology import NodeInfo, ClusterTopology

    # ── Read configuration from environment ──────────────────
    node_id = os.environ.get("ZENIC_NODE_ID", "")
    queues_str = os.environ.get("ZENIC_WORKER_QUEUES", "pipeline,saga,generation")
    queue_names = [q.strip() for q in queues_str.split(",") if q.strip()]
    heartbeat_interval = float(os.environ.get("ZENIC_HEARTBEAT_INTERVAL", "10"))
    lease_duration = float(os.environ.get("ZENIC_LEASE_DURATION", "120"))
    coordination_backend = os.environ.get("ZENIC_COORDINATION_BACKEND", "postgresql")

    # ── Determine backend type ───────────────────────────────
    if coordination_backend == "postgresql":
        backend_type = BackendType.POSTGRESQL
    else:
        backend_type = BackendType.MEMORY

    # ── Create backend ───────────────────────────────────────
    config = BackendConfig(
        backend_type=backend_type,
        connection_string=os.environ.get("DATABASE_URL_SYNC", ""),
        node_id=node_id,
        heartbeat_interval=heartbeat_interval,
        lease_duration=lease_duration,
    )
    backend = CoordinationBackend.create(config)

    # ── Create task queue ────────────────────────────────────
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(backend.connect())
    except Exception as exc:
        logger.error("Worker: Failed to connect backend: %s", exc)
        logger.info("Worker: Falling back to MemoryBackend")
        config.backend_type = BackendType.MEMORY
        backend = CoordinationBackend.create(config)
        loop.run_until_complete(backend.connect())

    queue = DistributedTaskQueue(
        backend=backend,
        default_lease_seconds=lease_duration,
    )
    loop.run_until_complete(queue.connect())

    # ── Create and configure worker ──────────────────────────
    worker_config = WorkerConfig(
        worker_id=node_id,
        queue_names=queue_names,
        lease_seconds=lease_duration,
        heartbeat_interval=heartbeat_interval,
    )

    worker = DistributedWorker(
        config=worker_config,
        queue=queue,
        backend=backend,
    )

    # ── Register task handlers ───────────────────────────────
    # Import and register handlers for known task types
    _register_handlers(worker)

    # ── Register in cluster topology ─────────────────────────
    topology = ClusterTopology(
        backend=backend,
        node_info=NodeInfo(
            node_id=worker_config.worker_id,
            capabilities={
                "task_types": list(worker._handlers.keys()),
                "queue_names": queue_names,
                "mode": "worker",
            },
        ),
        heartbeat_interval=heartbeat_interval,
    )
    loop.run_until_complete(topology.join())
    topology.start_heartbeat()

    # ── Signal handling for graceful shutdown ─────────────────
    def _signal_handler(signum: int, frame: Any) -> None:
        logger.info("Worker: Received signal %d, shutting down...", signum)
        worker.stop()
        loop.run_until_complete(topology.leave())
        loop.run_until_complete(queue.disconnect())
        loop.run_until_complete(backend.disconnect())
        sys.exit(0)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    # ── Start worker (blocking) ──────────────────────────────
    logger.info(
        "Worker: Starting %s (queues=%s, backend=%s)",
        worker_config.worker_id,
        queue_names,
        type(backend).__name__,
    )
    try:
        worker.start(blocking=True)
    except KeyboardInterrupt:
        logger.info("Worker: Interrupted, shutting down...")
    finally:
        worker.stop()
        loop.run_until_complete(topology.leave())
        loop.run_until_complete(queue.disconnect())
        loop.run_until_complete(backend.disconnect())
        loop.close()


def _register_handlers(worker: "DistributedWorker") -> None:
    """
    Register task handlers for known task types.

    This function imports and registers handlers for the ZENIC
    pipeline task types. Handlers are registered based on
    available modules.
    """
    # Register basic handlers that are always available
    def _handle_generic(task: dict) -> dict:
        """Generic task handler — logs and returns basic response."""
        logger.info(
            "Worker: Processing generic task %s (type=%s)",
            task.get("task_id", "")[:8],
            task.get("task_type", "unknown"),
        )
        return {"processed": True, "task_type": task.get("task_type")}

    worker.register_handler("generic", _handle_generic)

    # Try to register pipeline-specific handlers
    try:
        raise ImportError("DAGOrchestrator migrated to zenic-core Rust crate")  # from src.core.dag_parts.orchestrator import DAGOrchestrator
        # Pipeline handler would process DAG pipeline tasks
        worker.register_handler("pipeline", _handle_generic)
        worker.register_handler("saga_step_pipeline", _handle_generic)
    except ImportError:
        logger.debug("Worker: DAGOrchestrator not available for pipeline tasks")

    # code_generator & app_generator modules deleted — handlers removed
    # DEAD IMPORT REMOVED: from src.core.code_generator import CodeGenerator
    # DEAD IMPORT REMOVED: from src.core.app_generator import AppGenerator
    logger.debug("Worker: CodeGenerator/AppGenerator not available (modules deleted)")

    # Try to register reasoning handler
    try:
        from src.core.reasoning_engine import ReasoningEngine
        worker.register_handler("reasoning", _handle_generic)
    except ImportError:
        logger.debug("Worker: ReasoningEngine not available")

    # Register saga step handlers
    def _handle_saga_step(task: dict) -> dict:
        """Handle saga step execution."""
        payload = task.get("payload", {})
        saga_id = payload.get("saga_id", "")
        step_name = payload.get("step_name", "")
        logger.info(
            "Worker: Processing saga step '%s' for saga %s",
            step_name, saga_id[:8] if saga_id else "unknown",
        )
        return {"step_completed": True, "step_name": step_name}

    worker.register_handler("saga_step", _handle_saga_step)

    # Register compensation handlers
    def _handle_compensation(task: dict) -> dict:
        """Handle saga compensation step."""
        payload = task.get("payload", {})
        step_name = payload.get("step_name", "")
        logger.info(
            "Worker: Processing compensation for step '%s'",
            step_name,
        )
        return {"compensated": True, "step_name": step_name}

    worker.register_handler("compensation", _handle_compensation)

    logger.info(
        "Worker: Registered %d task handlers: %s",
        len(worker._handlers),
        list(worker._handlers.keys()),
    )


if __name__ == "__main__":
    main()
