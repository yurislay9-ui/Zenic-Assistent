#!/usr/bin/env python3
"""
ZENIC-AGENTS - Headless Server for Termux/proot-distro

Servidor OpenAI-Compatible SIN interfaz grafica. Disenado para correr en
Termux + proot-distro (Debian) en tu Redmi 12R Pro.

Uso:
  python3 main_headless.py                    # Modo interactivo
  python3 main_headless.py --port 5000        # Puerto custom
  python3 main_headless.py --ram-limit 4096   # Limite RAM en MB
  python3 main_headless.py --daemon           # Modo daemon (background)
"""

import sys
import os
import time
import logging
import argparse
import signal
import threading

# ============================================================
#  INICIALIZACION - Antes de importar modulos pesados
# ============================================================

from src.core.env_loader import load_env
load_env()

from src.core.shared.resource_governor import (
    tune_gc_for_arm, set_process_priority_low,
    limit_open_files, init_governor,
)

tune_gc_for_arm()
set_process_priority_low()
limit_open_files()

from src.core.shared.contracts import HAS_Z3
from src.core.shared.db_initializer import initialize_databases
from src.core.shared._version import ZENIC_VERSION_STR, ZENIC_FULL_NAME

# Feature flags
_ZENIC_USE_SNA = os.environ.get("ZENIC_USE_SNA", "1") == "1"
_ZENIC_USE_BLUEPRINTS = os.environ.get("ZENIC_USE_BLUEPRINTS", "1") == "1"

# Use DAGOrchestrator as primary, with ZenicOrchestrator as fallback
try:
    from src.core.dag_orchestrator import DAGOrchestrator
    _ORCHESTRATOR_CLASS = DAGOrchestrator
    _ORCHESTRATOR_NAME = f"DAGOrchestrator ({ZENIC_VERSION_STR})"
except ImportError:
    from src.core.orchestrator import ZenicOrchestrator
    _ORCHESTRATOR_CLASS = ZenicOrchestrator
    _ORCHESTRATOR_NAME = f"ZenicOrchestrator ({ZENIC_VERSION_STR})"

from src.server import (
    ZenicHTTPHandler, ThreadedHTTPServer,
    get_local_ip, configure_handler, RateLimiter,
)
from src.server.headless_cli import print_banner, run_interactive_loop

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("ZENIC")

START_TIME = time.time()


def main():
    parser = argparse.ArgumentParser(
        description=f"ZENIC-AGENTS {ZENIC_VERSION_STR} - Headless Server"
    )
    parser.add_argument('--port', type=int, default=5000, help='Puerto (default: 5000)')
    parser.add_argument('--host', type=str, default='0.0.0.0', help='Host (default: 0.0.0.0)')
    parser.add_argument('--ram-limit', type=int, default=4096, help='Limite RAM MB (default: 4096)')
    parser.add_argument('--daemon', action='store_true', help='Modo daemon')
    parser.add_argument('--debug', action='store_true', help='Modo debug')
    parser.add_argument('--server', type=str, default='stdlib', choices=['stdlib', 'fastapi'])
    parser.add_argument('--auth', action='store_true', help='Habilitar autenticacion')
    parser.add_argument('--sna', action='store_true', default=False, help='Habilitar SNA')
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Init governor + databases
    governor = init_governor(ram_limit_mb=args.ram_limit)
    initialize_databases()

    solver_name = "Z3" if HAS_Z3 else "AC-3"
    logger.info(f"{ZENIC_FULL_NAME} - Headless Server | Solver: {solver_name}")

    # Crear orchestrator
    orchestrator = _ORCHESTRATOR_CLASS()
    logger.info(f"Orchestrator: {_ORCHESTRATOR_NAME} [HYBRID MODE]")

    # Connect governor to ModelManager
    if hasattr(orchestrator, '_model_mgr'):
        governor.set_model_manager(orchestrator._model_mgr)

    # Reset circuit breakers
    _reset_circuit_breakers(orchestrator)

    # Preload models
    _preload_models(orchestrator)

    # Init AuthService
    auth_service = _init_auth(args)

    # ── Init SNA ──
    sna_engine = _init_sna(args)

    # ── Init Blueprints (Phase 5) ──
    blueprint_registry = None
    if _ZENIC_USE_BLUEPRINTS:
        from src.core.blueprints.boot import init_blueprint_registry
        project_root = os.path.dirname(os.path.abspath(__file__))
        blueprint_registry = init_blueprint_registry(
            project_root=project_root, sna_engine=sna_engine,
        )

    # ── Init Phase 6: Multi-Rol + Seguridad Completa ──
    phase6_status = None
    _ZENIC_USE_PHASE6 = os.environ.get("ZENIC_USE_PHASE6", "1") == "1"
    if _ZENIC_USE_PHASE6:
        try:
            from src.core.phase6_init import initialize_phase6
            phase6_status = initialize_phase6(start_defense_monitoring=True)
            ok_count = sum(1 for v in phase6_status.values() if v.get("status") == "ok")
            logger.info("Phase 6 (Multi-Rol + Seguridad): %d/%d components initialized", ok_count, len(phase6_status))
        except Exception as e:
            logger.warning("Phase 6 init failed: %s", e)

    # Rate limiter
    rate_limiter = _create_rate_limiter(args, auth_service)

    # Configure handler
    configure_handler(orchestrator, governor=governor,
                      start_time=START_TIME, platform_tag="termux-proot",
                      rate_limiter=rate_limiter)

    ip = get_local_ip()

    # ── FastAPI Server Mode ──
    if args.server == 'fastapi':
        try:
            from src.server.fastapi_app import run_fastapi_server
        except ImportError:
            logger.error("FastAPI no instalado. Usa --server stdlib")
            sys.exit(1)

        print_banner(ip, args.port, solver_name, governor, server_type="FastAPI (SaaS)")
        try:
            run_fastapi_server(
                orchestrator=orchestrator, host=args.host, port=args.port,
                auth_service=auth_service, rate_limiter=rate_limiter,
                governor=governor, platform_tag="termux-proot",
            )
        except KeyboardInterrupt:
            _shutdown(governor, sna_engine)
        return

    # ── Stdlib Server Mode ──
    print_banner(ip, args.port, solver_name, governor)

    try:
        server = ThreadedHTTPServer((args.host, args.port), ZenicHTTPHandler)
    except OSError as e:
        logger.error(f"No se pudo iniciar el servidor: {e}")
        sys.exit(1)

    def shutdown_handler(signum, frame):
        _shutdown(governor, sna_engine)
        server.shutdown()
        from src.server.http_handler import _shutdown_loop
        _shutdown_loop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    if args.daemon:
        logger.info("Running as daemon on port %d", args.port)
        server.serve_forever()
    else:
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        logger.info(f"Server listening on http://{ip}:{args.port}")

        run_interactive_loop(
            orchestrator=orchestrator, governor=governor,
            sna_engine=sna_engine, blueprint_registry=blueprint_registry,
        )

        _shutdown(governor, sna_engine)
        server.shutdown()
        from src.server.http_handler import _shutdown_loop
        _shutdown_loop()
        logger.info("Server stopped.")


# ── Helper Functions ──────────────────────────────────────────

def _reset_circuit_breakers(orchestrator: object) -> None:
    """Reset circuit breakers on startup."""
    if hasattr(orchestrator, '_agent_runner') and orchestrator._agent_runner is not None:
        cb = getattr(orchestrator._agent_runner, '_circuit_breaker', None)
        if cb is not None:
            cb.reset()
    if hasattr(orchestrator, '_model_mgr') and orchestrator._model_mgr.ai_loaded:
        ai = orchestrator._model_mgr.mini_ai_engine
        if hasattr(ai, '_verdict_cb') and ai._verdict_cb is not None:
            ai._verdict_cb.reset()


def _preload_models(orchestrator: object) -> None:
    """Preload AI models if configured."""
    preload = os.environ.get("ZENIC_PRELOAD_MODELS", "1") == "1"
    if not preload or not hasattr(orchestrator, '_model_mgr'):
        return
    logger.info("Preloading AI models...")
    try:
        _mgr = orchestrator._model_mgr
        t0 = time.time()
        _ = _mgr.semantic_engine
        t1 = time.time()
        logger.info(f"  SemanticEngine loaded in {t1-t0:.1f}s")
        _ = _mgr.mini_ai_engine
        t2 = time.time()
        logger.info(f"  MiniAIEngine loaded in {t2-t1:.1f}s")
    except Exception as e:
        logger.warning(f"Model preload failed: {e}")


def _init_auth(args: argparse.Namespace) -> object:
    """Initialize AuthService if needed."""
    if not (args.auth or args.server == 'fastapi'):
        return None
    try:
        from src.core.auth_service import AuthService
        auth_service = AuthService()
        auth_service.ensure_admin()
        logger.info("AuthService: initialized")
        return auth_service
    except Exception as e:
        logger.warning(f"AuthService init failed: {e}")
        return None


def _init_sna(args: argparse.Namespace) -> object:
    """Initialize SNA Engine if enabled."""
    if not (_ZENIC_USE_SNA or args.sna):
        return None
    try:
        from src.core.sna import get_sna_engine
        import asyncio
        sna_engine = get_sna_engine()
        try:
            from src.core.executors.dispatch_action import get_default_dispatcher
            sna_engine.set_dispatcher(get_default_dispatcher())
        except Exception:
            pass
        loaded = sna_engine.load_default_monitors()
        logger.info("SNA: Loaded %d default monitors", loaded)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(sna_engine.start())
            else:
                loop.run_until_complete(sna_engine.start())
        except RuntimeError:
            logger.info("SNA: Will start with server event loop")
        return sna_engine
    except Exception as e:
        logger.warning("SNA init failed: %s", e)
        return None


def _create_rate_limiter(args: argparse.Namespace, auth_service: object) -> object:
    """Create the appropriate rate limiter."""
    _rl_rpm = int(os.environ.get("ZENIC_RATE_LIMIT_RPM", str(max(1, args.ram_limit // 64))))
    _rl_burst = int(os.environ.get("ZENIC_RATE_LIMIT_BURST", "20"))
    _rl_concurrent = int(os.environ.get("ZENIC_RATE_LIMIT_CONCURRENT", "60"))

    if auth_service is not None:
        try:
            from src.server.tenant_rate_limiter import TenantRateLimiter
            return TenantRateLimiter(
                max_requests_per_minute=_rl_rpm, burst_size=_rl_burst,
                global_max_concurrent=_rl_concurrent,
                default_user_rpm=_rl_rpm, default_user_burst=_rl_burst,
            )
        except ImportError:
            pass

    return RateLimiter(
        max_requests_per_minute=_rl_rpm, burst_size=_rl_burst,
        global_max_concurrent=_rl_concurrent,
    )


def _shutdown(governor: object, sna_engine: object = None) -> None:
    """Graceful shutdown of subsystems."""
    governor.stop_monitoring()
    if sna_engine:
        try:
            import asyncio
            asyncio.get_event_loop().run_until_complete(sna_engine.stop())
        except Exception:
            pass
    # Phase 6: Stop defense monitoring and license heartbeat
    try:
        from src.core.defense.anti_tampering import reset_anti_tampering
        from src.core.defense.integrity import reset_integrity_verifier
        from src.core.license.manager import reset_license_manager
        reset_anti_tampering()
        reset_integrity_verifier()
        reset_license_manager()
    except Exception:
        pass


if __name__ == '__main__':
    main()
