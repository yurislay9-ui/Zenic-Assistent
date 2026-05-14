"""
Zenic-Agents Asistente - Headless CLI Helpers (Phase 5)

Extracted from main_headless.py to keep it under 400 lines.
Contains banner printing and interactive CLI loop.
"""

from __future__ import annotations

import os
import sys
import threading
from typing import Any, Dict, Optional


def print_banner(
    ip: str, port: int, solver_name: str,
    governor: Any, server_type: str = "HYBRID MODE",
) -> None:
    """Print the startup banner."""
    from src.core.shared._version import ZENIC_VERSION_STR
    res = governor.get_status() if governor else {}
    idle_min = int(os.environ.get("ZENIC_MODEL_IDLE_TIMEOUT", "3600")) // 60
    ram_budget = os.environ.get("ZENIC_RAM_BUDGET_MB", "4096")
    auto_unload = "ON" if os.environ.get("ZENIC_AUTO_UNLOAD", "1") == "1" else "OFF"
    rl_concurrent = os.environ.get("ZENIC_RATE_LIMIT_CONCURRENT", "60")
    banner = f"""
+==============================================================+
|  ZENIC-AGENTS {ZENIC_VERSION_STR} - HEADLESS SERVER [{server_type}]    
|  Motor de IA Quirurgico Local ({solver_name})                   
+==============================================================+
|                                                              |
|  Conecta Cline/Aide/OpenCode a:                              |
|  http://{ip}:{port}/v1                                       |
|                                                              |
|  Endpoints:                                                  |
|    GET  /v1/models        - Modelos disponibles              |
|    POST /v1/chat/completions - Chat completion               |
|    GET  /health           - Status + recursos                |
|                                                              |
|  Recursos (Hybrid Lazy Loading):                             |
|    Solver: {solver_name} | MCTS: ARM-optimized                  |
|    RAM: {res.get('ram_usage_mb', 0):.0f}MB / {res.get('ram_limit_mb', '?')}MB limite           |
|    Models: Lazy (se cargan al primer request)               |
|    Auto-unload: {auto_unload} ({idle_min} min idle) | Budget: {ram_budget}MB           |
|    Rate limit: {rl_concurrent} concurrent | GC tuned for ARM        |
|    Priority: low                                             |
|                                                              |
|  Ctrl+C para detener                                         |
+==============================================================+
"""
    print(banner)


def run_interactive_loop(
    orchestrator: Any,
    governor: Any,
    sna_engine: Any = None,
    blueprint_registry: Any = None,
) -> None:
    """Run the interactive CLI loop (stdin commands)."""
    try:
        while True:
            try:
                cmd = input("").strip()
                if cmd.lower() in ('quit', 'exit', 'q', 'stop'):
                    break
                elif cmd.lower() == 'status':
                    _cmd_status(orchestrator, governor)
                elif cmd.lower() == 'models':
                    _cmd_models(orchestrator)
                elif cmd.lower() == 'sna':
                    _cmd_sna(sna_engine)
                elif cmd.lower() == 'blueprints':
                    _cmd_blueprints(blueprint_registry)
                elif cmd.lower() == 'help':
                    print("  Commands: status | models | sna | blueprints | quit | help")
            except EOFError:
                break
    except KeyboardInterrupt:
        pass


def _cmd_status(orchestrator: Any, governor: Any) -> None:
    """Handle 'status' CLI command."""
    status = governor.get_status()
    print(f"  CPU: {status['cpu_usage_pct']}% | RAM: {status['ram_usage_mb']}MB/{status['ram_limit_mb']}MB")
    print(f"  Throttle: {status['thermal_throttle']} | MCTS: {status['adaptive_mcts_sims']} sims")
    print(f"  Requests: {status['stats']['requests_served']} | GC forced: {status['stats']['gc_forced']}")
    if hasattr(orchestrator, '_model_mgr'):
        ms = orchestrator._model_mgr.get_status()
        for name, info in ms.get('models', {}).items():
            idle = f" (idle {info.get('idle_s', 0)}s)" if 'idle_s' in info else ""
            print(f"  {name}: {info['status']}{idle}")


def _cmd_models(orchestrator: Any) -> None:
    """Handle 'models' CLI command."""
    if hasattr(orchestrator, '_model_mgr'):
        ms = orchestrator._model_mgr.stats
        print(f"  SemanticEngine: {'LOADED' if ms['semantic_loaded'] else 'UNLOADED'} (loads={ms['semantic_loads']}, unloads={ms['semantic_unloads']})")
        print(f"  MiniAIEngine:  {'LOADED' if ms['ai_loaded'] else 'UNLOADED'} (loads={ms['ai_loads']}, unloads={ms['ai_unloads']})")
        print(f"  Auto-unloads: {ms['auto_unloads']} | RAM: {ms['current_ram_mb']}MB")
    else:
        print("  ModelManager not available")


def _cmd_sna(sna_engine: Any) -> None:
    """Handle 'sna' CLI command."""
    if sna_engine:
        s = sna_engine.detailed_stats
        eng = s.get('engine', {})
        sched = s.get('scheduler', {})
        am = s.get('alert_manager', {})
        print(f"  SNA: checks={eng.get('total_checks',0)} triggered={eng.get('total_triggered',0)}")
        print(f"  Monitors: {sched.get('active_monitors',0)} active | State: {sched.get('state','stopped')}")
        print(f"  Alerts: {am.get('active_alerts',0)} active | Created: {am.get('created',0)}")
    else:
        print("  SNA not enabled (use --sna or ZENIC_USE_SNA=1)")


def _cmd_blueprints(blueprint_registry: Any) -> None:
    """Handle 'blueprints' CLI command."""
    if blueprint_registry:
        ov = blueprint_registry.overview
        print(f"  Blueprints: {ov['total_blueprints']} registered | {ov['total_certified']} certified")
        print(f"  Domains: {', '.join(ov['domains'][:10])}")
        print(f"  Active tenants: {ov['active_tenants']}")
    else:
        print("  Blueprints not enabled (use ZENIC_USE_BLUEPRINTS=1)")
