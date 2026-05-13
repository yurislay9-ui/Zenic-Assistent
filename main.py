"""
ZENIC-AGENTS - Motor de IA Quirurgico Local
Servidor OpenAI-Compatible para Cline, Aide, OpenCode y mas.

Usa modulos src/core/ con Z3 SMT Solver (con fallback AC-3),
MCTS real, Ejecucion Simbolica real, Timeout enforcement real,
Cache de Teoremas con Skeleton Hash, Protocolo Abortivo,
y Razonamiento Parcial con tool_calls.

Interfaz TUI (Terminal UI) con Textual — funciona en Termux,
proot-distro, VPS y cualquier terminal sin dependencias graficas.

Modo de uso:
  1. Pulsa INICIAR MOTOR
  2. Conecta Cline/Aide a: http://TU_IP:5000/v1
  3. El motor procesa tus peticiones con 8 niveles de razonamiento
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
# Default is v16 DAGOrchestrator (production-ready, tested with Cline)
import os as _os
if _os.environ.get("ZENIC_USE_UNIFIED_DAG", "0") == "1":
    try:
        from src.core.dag_parts.unified_orchestrator import UnifiedDAGOrchestrator as _Orchestrator
    except ImportError:
        from src.core.dag_orchestrator import DAGOrchestrator as _Orchestrator
else:
    try:
        from src.core.dag_orchestrator import DAGOrchestrator as _Orchestrator
    except ImportError:
        from src.core.orchestrator import ZenicOrchestrator as _Orchestrator

from src.server import (
    ZenicHTTPHandler, ThreadedHTTPServer,
    get_local_ip, configure_handler, RateLimiter,
)

from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Button, Input, Label, Static
from textual.reactive import reactive
from textual import work

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ZENIC")

IS_ANDROID = 'ANDROID_ARGUMENT' in os.environ


# ============================================================
#  INTERFAZ TEXTUAL (TUI)
# ============================================================

class ZenicTUIApp(App):
    """ZENIC-AGENTS con servidor OpenAI-compatible — Interfaz TUI."""

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
        ("i", "toggle_engine", "Iniciar/Detener"),
        ("t", "focus_input", "Probar"),
    ]

    server_running: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        self.engine = _Orchestrator()
        self.server = None
        self._log_lines: list[str] = []

        solver_name = "Z3" if HAS_Z3 else "AC-3"

        # Title
        yield Label(
            f"ZENIC-AGENTS {ZENIC_VERSION_STR}\n"
            f"Motor de IA Quirurgico Local ({solver_name})",
            id="title-label",
        )

        # IP Info
        yield Label(
            "Conecta Cline/Aide/OpenCode a:\nhttp://0.0.0.0:5000/v1",
            id="ip-label",
        )

        # Status
        yield Label("Motor Apagado", id="status-label")

        # Start/Stop Button
        btn = Button(f"INICIAR MOTOR ZENIC {ZENIC_VERSION_STR}", id="start-btn", variant="primary")
        yield btn

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
            f"Motor {ZENIC_VERSION_STR} listo. Pulsa INICIAR MOTOR para activar el servidor.\n\n"
            f"NOVEDADES {ZENIC_VERSION_STR}:\n"
            f"- {solver_name} SMT Solver (Z3 si disponible, AC-3 fallback)\n"
            f"- MCTS real (UCB1, 100 simulaciones, depth 5)\n"
            f"- Ejecucion Simbolica Acotada real\n"
            f"- Timeout enforcement real (15s quirurgico, 5s moderado)\n"
            f"- K-Paths basado en grafo de dependencias\n"
            f"- Protocolo Abortivo (auto-subdivision en timeout)\n"
            f"- Razonamiento Parcial con tool_calls\n"
            f"- Cache de Teoremas con Skeleton Hash\n"
            f"- Configuracion YAML conectada\n"
            f"- MacroRouter con firmas topologicas del AST\n"
            f"- Generacion de codigo contextual\n\n"
            f"COMO CONECTAR CLINE:\n"
            f"1. Inicia el motor en esta app\n"
            f"2. En VS Code, configura Cline:\n"
            f"   - API Provider: OpenAI Compatible\n"
            f"   - Base URL: http://TU_IP:5000/v1\n"
            f"   - Model: zenic-agents\n"
            f"3. Cline enviara peticiones a tu telefono\n\n"
            f"ATAJOS DE TECLADO:\n"
            f"  [i] Iniciar/Detener motor  [t] Probar  [q] Salir"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-btn":
            self.toggle_engine()
        elif event.button.id == "test-btn":
            self._test_local()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "test-input":
            self._test_local()

    def action_toggle_engine(self) -> None:
        self.toggle_engine()

    def action_focus_input(self) -> None:
        self.query_one("#test-input", Input).focus()

    def toggle_engine(self) -> None:
        if self.server_running:
            self._stop_engine()
        else:
            self._start_engine()

    def _start_engine(self) -> None:
        ip = get_local_ip()
        self._update_status(f"Iniciando motor {ZENIC_VERSION_STR}...", "warning")
        start_btn = self.query_one("#start-btn", Button)
        start_btn.disabled = True

        # Configurar handler compartido con rate limiter basico para TUI
        rate_limiter = RateLimiter(
            max_requests_per_minute=30,
            burst_size=5,
            global_max_concurrent=10,
        )
        configure_handler(self.engine, governor=None, platform_tag="tui",
                          rate_limiter=rate_limiter)

        def run_server():
            try:
                self.server = ThreadedHTTPServer(('0.0.0.0', 5000), ZenicHTTPHandler)
                self.server_running = True
                self.call_from_thread(self._update_status_running, ip)
                self.server.serve_forever()
            except OSError as e:
                self.call_from_thread(self._update_status_error, str(e))
            except Exception as e:
                self.call_from_thread(self._update_status_error, str(e))

        threading.Thread(target=run_server, daemon=True).start()

    def _stop_engine(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server = None
        self.server_running = False
        self._update_status("Motor Apagado", "error")
        start_btn = self.query_one("#start-btn", Button)
        start_btn.label = f"INICIAR MOTOR ZENIC {ZENIC_VERSION_STR}"
        start_btn.variant = "primary"
        start_btn.disabled = False
        self._add_log("Motor detenido.")

    def _update_status(self, text: str, style: str = "error") -> None:
        status_label = self.query_one("#status-label", Label)
        status_label.update(text)
        # Update color based on status
        if style == "success":
            status_label.styles.color = "green"
        elif style == "warning":
            status_label.styles.color = "yellow"
        else:
            status_label.styles.color = "red"

    def _update_status_running(self, ip: str) -> None:
        solver_name = "Z3" if HAS_Z3 else "AC-3"
        self._update_status(
            f"Motor {ZENIC_VERSION_STR} ACTIVO ({solver_name}) - {ip}:5000",
            "success",
        )
        start_btn = self.query_one("#start-btn", Button)
        start_btn.label = "DETENER MOTOR"
        start_btn.variant = "error"
        start_btn.disabled = False
        self._add_log(f"Motor {ZENIC_VERSION_STR} activo. {solver_name} + MCTS + SymbolicExec reales.")

    def _update_status_error(self, error: str) -> None:
        self._update_status(f"Error: {error}", "error")
        start_btn = self.query_one("#start-btn", Button)
        start_btn.label = "REINTENTAR"
        start_btn.variant = "primary"
        start_btn.disabled = False
        self._add_log(f"Error: {error}")

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
    """Graceful shutdown: stop server, close DB connections."""
    global _zenic_app
    try:
        if _zenic_app is not None:
            if _zenic_app.server:
                _zenic_app.server.shutdown()
    except Exception:
        pass
    try:
        from src.server.http_handler import _shutdown_loop
        _shutdown_loop()
    except Exception:
        pass

atexit.register(_cleanup)

if __name__ == '__main__':
    initialize_databases()
    solver_name = "Z3" if HAS_Z3 else "AC-3"
    logger.info(f"{ZENIC_FULL_NAME} - Local Surgical AI Engine (TUI)")
    logger.info(f"Solver: {solver_name} | MCTS Real | Symbolic Exec Real | Timeout Real | Skeleton Hash")
    logger.info("OpenAI-compatible server for Cline, Aide, OpenCode")

    _zenic_app = ZenicTUIApp()
    _zenic_app.run()
