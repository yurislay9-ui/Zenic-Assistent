#!/usr/bin/env python3
"""
ZENIC-AGENTS - Headless CLI for Termux/proot-distro

CLI local SIN servidor HTTP. Disenado para correr en
Termux + proot-distro (Debian) en tu Redmi 12R Pro.

NOTA: El servidor HTTP (src/server/) ha sido eliminado.
Este entry point ahora solo ejecuta el motor localmente
via CLI interactivo, sin servidor HTTP.

Uso:
  python3 main_headless.py                    # Modo interactivo
  python3 main_headless.py --ram-limit 4096   # Limite RAM en MB
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

# Phase 5 — Deterministic mode: Install global patches for production determinism.
# Controlled via ZENIC_DETERMINISTIC env var (default "1" = enabled).
# When enabled, uuid.uuid4(), random.*, and (optionally) time.time() are
# replaced with deterministic implementations seeded from SeedManager.
_ZENIC_DETERMINISTIC = os.environ.get("ZENIC_DETERMINISTIC", "1") == "1"
if _ZENIC_DETERMINISTIC:
    from src.core.shared.deterministic import (
        set_global_seed, install_uuid4_patch, install_random_patch,
        get_global_seed,
    )
    _seed = get_global_seed()  # Resolves from ZENIC_DETERMINISTIC_SEED or default 0xC0FFEE
    set_global_seed(_seed)
    install_uuid4_patch()
    install_random_patch()
    # time.time() patch is optional — only enable for full replay mode
    if os.environ.get("ZENIC_DETERMINISTIC_TIME", "0") == "1":
        from src.core.shared.deterministic import install_time_patch
        install_time_patch(increment=0.001)

tune_gc_for_arm()
set_process_priority_low()
limit_open_files()

from src.core.shared.contracts import HAS_Z3
from src.core.shared.db_initializer import initialize_databases
from src.core.shared._version import ZENIC_VERSION_STR, ZENIC_FULL_NAME

# Feature flags
_ZENIC_USE_SNA = os.environ.get("ZENIC_USE_SNA", "1") == "1"
_ZENIC_USE_BLUEPRINTS = os.environ.get("ZENIC_USE_BLUEPRINTS", "1") == "1"

# dag_orchestrator migrated to Rust — use ZenicOrchestrator directly
from src.core.orchestrator import ZenicOrchestrator
_ORCHESTRATOR_CLASS = ZenicOrchestrator
_ORCHESTRATOR_NAME = f"ZenicOrchestrator ({ZENIC_VERSION_STR})"

# Server module removed — no more HTTP server imports
# from src.server import (ZenicHTTPHandler, ThreadedHTTPServer, ...)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("ZENIC")

START_TIME = time.time()


def main():
    parser = argparse.ArgumentParser(
        description=f"ZENIC-AGENTS {ZENIC_VERSION_STR} - Local Engine CLI"
    )
    parser.add_argument('--ram-limit', type=int, default=4096, help='Limite RAM MB (default: 4096)')
    parser.add_argument('--debug', action='store_true', help='Modo debug')
    parser.add_argument('--sna', action='store_true', default=False, help='Habilitar SNA')
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Init governor + databases
    governor = init_governor(ram_limit_mb=args.ram_limit)
    initialize_databases()

    solver_name = "Z3" if HAS_Z3 else "AC-3"
    logger.info(f"{ZENIC_FULL_NAME} - Local Engine CLI | Solver: {solver_name}")
    logger.info("NOTE: HTTP server removed — local engine only")

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

    # ── Interactive CLI Loop ──
    print(f"\n{'=' * 60}")
    print(f"  ZENIC-AGENTS {ZENIC_VERSION_STR} — Local Engine CLI")
    print(f"  Solver: {solver_name} | Orchestrator: {_ORCHESTRATOR_NAME}")
    print(f"  NOTE: HTTP server removed — local engine only")
    print(f"{'=' * 60}")
    print(f"  Type queries to test the engine. Type 'quit' to exit.")
    print(f"{'=' * 60}\n")

    _run_interactive_loop(orchestrator, governor, sna_engine, blueprint_registry)

    _shutdown(governor, sna_engine)
    logger.info("Engine stopped.")


# ── Helper Functions ──────────────────────────────────────────

def _run_interactive_loop(orchestrator, governor, sna_engine=None, blueprint_registry=None):
    """Simple interactive loop for local engine testing."""
    import asyncio
    while True:
        try:
            user_input = input("zenic> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break

        if user_input == "status":
            _print_status(orchestrator, governor, sna_engine)
            continue

        # Execute query through the engine
        try:
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(orchestrator.execute(user_input))
            loop.close()

            status = result.get('status', 'N/A')
            route = result.get('route', 'N/A')
            crit = result.get('criticality', 'N/A')
            time_ms = result.get('processing_time_ms', 0)
            print(f"  Status: {status} | Route: {route} | Crit: {crit} | Time: {time_ms}ms")

            if result.get('error'):
                print(f"  Error: {result['error']}")
            if result.get('explanations'):
                for exp in result['explanations']:
                    print(f"  {exp}")
        except Exception as e:
            print(f"  Error: {e}")


def _print_status(orchestrator, governor, sna_engine=None):
    """Print current engine status."""
    print(f"  Orchestrator: {type(orchestrator).__name__}")
    if hasattr(orchestrator, '_model_mgr'):
        mgr = orchestrator._model_mgr
        print(f"  AI Loaded: {mgr.ai_loaded}")
        print(f"  Semantic Loaded: {mgr.semantic_loaded}")
    print(f"  Governor RAM limit: {governor._ram_limit_mb}MB")
    if sna_engine:
        print(f"  SNA: active")


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
            logger.info("SNA: Will start with event loop")
        return sna_engine
    except Exception as e:
        logger.warning("SNA init failed: %s", e)
        return None


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
