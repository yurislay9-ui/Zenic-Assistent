"""
ZENIC-AGENTS - Motor de IA Quirurgico Local
TUI Entry Point — uses core engine only (server module removed).

Usa modulos src/core/ con Z3 SMT Solver (con fallback AC-3),
MCTS real, Ejecucion Simbolica real, Timeout enforcement real,
Cache de Teoremas con Skeleton Hash, Protocolo Abortivo,
y Razonamiento Parcial con tool_calls.

Interfaz TUI (Terminal UI) con Textual — funciona en Termux,
proot-distro, VPS y cualquier terminal sin dependencias graficas.

NOTA: El servidor OpenAI-compatible (src/server/) ha sido eliminado.
Este entry point ahora solo ejecuta el motor localmente via TUI,
sin servidor HTTP. Para pruebas locales, usa el campo de texto.
"""

import os
import logging
import threading
import atexit

# Cargar .env ANTES de cualquier otro import (variables de entorno)
from src.core.env_loader import load_env
load_env()

from src.core.shared.contracts import HAS_Z3
from src.core.shared.db_initializer import initialize_databases
from src.core.shared._version import ZENIC_VERSION_STR, ZENIC_FULL_NAME

# R3: Support ZENIC_USE_UNIFIED_DAG=1 for v18 experimental pipeline
# dag_orchestrator migrated to Rust — fallback chain skips it entirely
import os as _os
if _os.environ.get("ZENIC_USE_UNIFIED_DAG", "0") == "1":
    try:
        from src.core.dag_parts.unified_orchestrator import UnifiedDAGOrchestrator as _Orchestrator  # type: ignore[import-unresolved]
    except ImportError:
        from src.core.orchestrator import ZenicOrchestrator as _Orchestrator
else:
    from src.core.orchestrator import ZenicOrchestrator as _Orchestrator

# Server module removed — no more HTTP server imports
# from src.server import (ZenicHTTPHandler, ThreadedHTTPServer, ...)

from textual.app import App, ComposeResult  # type: ignore[import-unresolved]
from textual.containers import Vertical, VerticalScroll  # type: ignore[import-unresolved]
from textual.widgets import Button, Input, Label, Static  # type: ignore[import-unresolved]
from textual.reactive import reactive  # type: ignore[import-unresolved]
from textual import work  # type: ignore[import-unresolved]

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ZENIC")

IS_ANDROID = 'ANDROID_ARGUMENT' in os.environ


# ============================================================
#  INTERFAZ TEXTUAL (TUI)
# ============================================================

class ZenicTUIApp(App):
    """ZENIC-AGENTS Motor de IA Quirurgico Local — Interfaz TUI.

    NOTE: The OpenAI-compatible HTTP server has been removed.
    This TUI now runs the engine locally only — no server startup.
    """

    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }

    #title-label {
        text-align: center;
        padding: 1 2;
        text-style: bold;
        color: $text;
        background: $primary;
    }

    #ip-label {
        text-align: center;
        padding: 0 2;
        color: $warning;
        background: $surface;
    }

    #status-label {
        text-align: center;
        padding: 0 2;
        color: $error;
        background: $surface;
    }

    #start-btn {
        margin: 1 2;
        height: 3;
    }

    #start-btn.running {
        background: $error;
    }

    #start-btn.stopped {
        background: $primary;
    }

    #test-input {
        margin: 0 2;
    }

    #test-btn {
        margin: 0 2;
        height: 3;
        background: $success;
    }

    #log-area {
        margin: 1 2;
        border: round $primary;
        padding: 0 1;
        height: 1fr;
        background: $surface;
    }

    .log-content {
        color: $text-muted;
    }
    """

    BINDINGS = [
        ("q", "quit", "Salir"),
        ("t", "focus_input", "Probar"),
    ]

    engine_running: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        self.engine = _Orchestrator()
        self._log_lines: list[str] = []

        solver_name = "Z3" if HAS_Z3 else "AC-3"

        # Title
        yield Label(
            f"ZENIC-AGENTS {ZENIC_VERSION_STR}\n"
            f"Motor de IA Quirurgico Local ({solver_name})",
            id="title-label",
        )

        # Info
        yield Label(
            "Modo local (sin servidor HTTP)\n"
            "Usa el campo de texto para probar el motor",
            id="ip-label",
        )

        # Status
        yield Label("Motor Listo", id="status-label")

        # Test Input
        yield Input(
            placeholder="Prueba local: 'crear modulo auth.py'",
            id="test-input",
        )

        # Test Button
        yield Button("PROBAR LOCALMENTE", id="test-btn", variant="success")

        # Log Area
        with VerticalScroll(id="log-area"):
            yield Static(self._initial_log_text(solver_name), classes="log-content")

    def _initial_log_text(self, solver_name: str) -> str:
        return (
            f"Motor {ZENIC_VERSION_STR} listo. Escribe una consulta y pulsa PROBAR.\n\n"
            f"NOVEDADES {ZENIC_VERSION_STR}:\n"
            f"- {solver_name} SMT Solver (Z3 si disponible, AC-3 fallback)\n"
            f"- MCTS real (UCB1, 100 simulaciones, depth 5)\n"
            f"- Ejecucion Simbolica Acotada real\n"
            f"- Timeout enforcement real (15s quirurgico, 5s moderado)\n"
            f"- K-Paths basado en grafo de dependencias\n"
            f"- Protocolo Abortivo (auto-subdivision en timeout)\n"
            f"- Cache de Teoremas con Skeleton Hash\n"
            f"- Configuracion YAML conectada\n"
            f"- MacroRouter con firmas topologicas del AST\n\n"
            f"NOTA: El servidor HTTP ha sido eliminado.\n"
            f"Este TUI ahora ejecuta solo el motor localmente.\n\n"
            f"ATAJOS DE TECLADO:\n"
            f"  [t] Probar  [q] Salir"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "test-btn":
            self._test_local()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "test-input":
            self._test_local()

    def action_focus_input(self) -> None:
        self.query_one("#test-input", Input).focus()

    def _test_local(self) -> None:
        test_input = self.query_one("#test-input", Input)
        msg = test_input.value.strip()
        if not msg:
            return
        self._add_log(f"\n>> Local: {msg}")
        test_btn = self.query_one("#test-btn", Button)
        test_btn.disabled = True
        test_input.value = ""
        threading.Thread(target=self._run_local_test, args=(msg,), daemon=True).start()

    def _run_local_test(self, msg: str) -> None:
        try:
            import asyncio
            loop = asyncio.new_event_loop()
            result = loop.run_until_complete(self.engine.execute(msg))
            loop.close()
            solver_name = "Z3" if HAS_Z3 else "AC-3"
            output = f"ZENIC {ZENIC_VERSION_STR} - {result['status']}\n"
            output += f"Route: {result.get('route', 'N/A')} | Crit: {result.get('criticality', 'N/A')}\n"
            output += f"Time: {result.get('processing_time_ms', 0)}ms | Hash: {result.get('hash', 'N/A')}\n"
            output += f"Solver({solver_name}): {result.get('solver_status', 'N/A')} | MCTS: {result.get('mcts_simulations', 0)} sims\n"
            if result.get('paths_explored'):
                output += f"Paths: {result.get('paths_explored', 0)} explored, {result.get('paths_pruned', 0)} pruned\n"
            if result.get('partial_reasoning'):
                output += "PROTOCOL: Razonamiento Parcial - subdividiendo tarea\n"
            if result.get('explanations'):
                for exp in result['explanations']:
                    output += f"  {exp}\n"
            if result.get('code'):
                output += f"\nCode:\n{result['code']}\n"
            if result.get('error'):
                output += f"\nError: {result['error']}\n"
        except Exception as e:
            output = f"Error: {str(e)}"
        self.call_from_thread(self._update_test_result, output)

    def _update_test_result(self, text: str) -> None:
        self._add_log(text)
        test_btn = self.query_one("#test-btn", Button)
        test_btn.disabled = False

    def _add_log(self, text: str) -> None:
        self._log_lines.append(text)
        if len(self._log_lines) > 200:
            self._log_lines = self._log_lines[-200:]
        try:
            log_content = self.query_one(".log-content", Static)
            log_content.update("\n".join(self._log_lines))
            # Auto-scroll to bottom
            scroll = self.query_one("#log-area", VerticalScroll)
            scroll.scroll_end(animate=False)
        except Exception:
            pass


# ============================================================
#  PUNTO DE ENTRADA
# ============================================================

_zenic_app: ZenicTUIApp | None = None


def _cleanup():
    """Graceful shutdown: close DB connections."""
    global _zenic_app
    # Server module removed — no more HTTP server cleanup needed

atexit.register(_cleanup)

if __name__ == '__main__':
    initialize_databases()
    solver_name = "Z3" if HAS_Z3 else "AC-3"
    logger.info(f"{ZENIC_FULL_NAME} - Local Surgical AI Engine (TUI)")
    logger.info(f"Solver: {solver_name} | MCTS Real | Symbolic Exec Real | Timeout Real | Skeleton Hash")
    logger.info("NOTE: HTTP server removed — local engine only")

    _zenic_app = ZenicTUIApp()
    _zenic_app.run()
