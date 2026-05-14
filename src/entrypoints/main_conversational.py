"""
Zenic-Agents — Modo Conversacional Entry Point.

Inicia el servidor del asistente conversacional.
Reutiliza el motor DAG Core si esta disponible.

Uso:
    python main_conversational.py                          # Modo conversacional standalone
    python main_conversational.py --port 5000              # Puerto personalizado
    python main_conversational.py --with-engine            # Con motor DAG Core
    python main_conversational.py --with-engine --auth     # Con auth del motor

El asistente funciona en dos modos:
  1. Standalone: Solo conversacional, sin motor de codigo
  2. Con Engine: Conectado al motor DAG Core para codigo,
     automatizaciones y razonamiento avanzado
"""

import argparse
import logging
import sys

from src.core.conversational.config.env import load_agents_config
from src.core.conversational.config.constants import APP_NAME, APP_VERSION
from src.core.conversational.utils.logger import setup_logging

logger = logging.getLogger("zenic_agents.conversational")


def parse_args() -> argparse.Namespace:
    """Parsea argumentos de linea de comandos."""
    parser = argparse.ArgumentParser(
        description=f"{APP_NAME} v{APP_VERSION}",
    )
    parser.add_argument(
        "--host", type=str, default=None,
        help="Host de bind (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Puerto del servidor (default: 5000)",
    )
    parser.add_argument(
        "--with-engine", action="store_true",
        help="Conectar con el motor DAG Core",
    )
    parser.add_argument(
        "--auth", action="store_true",
        help="Habilitar autenticacion del motor",
    )
    parser.add_argument(
        "--log-level", type=str, default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nivel de log",
    )
    parser.add_argument(
        "--log-file", type=str, default=None,
        help="Archivo de log (con rotacion)",
    )
    return parser.parse_args()


def load_zenic_engine(auth: bool = False) -> object:
    """
    Carga el orquestador DAG Core si esta disponible.

    Returns:
        Instancia del orquestador o None.
    """
    try:
        # Intentar cargar UnifiedDAGOrchestrator (59 nodos)
        import os
        os.environ["ZENIC_USE_UNIFIED_DAG"] = "1"
        from src.core.dag_parts.unified_orchestrator import UnifiedDAGOrchestrator
        engine = UnifiedDAGOrchestrator()
        logger.info("Motor DAG Core (UnifiedDAG 59 nodos) cargado exitosamente")
        return engine
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"No se pudo cargar UnifiedDAGOrchestrator: {e}")

    try:
        # Fallback a DAGOrchestrator
        from src.core.dag_orchestrator import DAGOrchestrator
        engine = DAGOrchestrator()
        logger.info("Motor DAG Core (DAGOrchestrator) cargado exitosamente")
        return engine
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"No se pudo cargar DAGOrchestrator: {e}")

    try:
        # Fallback a ZenicOrchestrator
        from src.core.orchestrator import ZenicOrchestrator
        engine = ZenicOrchestrator()
        logger.info("Motor DAG Core (ZenicOrchestrator) cargado exitosamente")
        return engine
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"No se pudo cargar ZenicOrchestrator: {e}")

    logger.warning("Ningun motor DAG Core disponible. Modo standalone.")
    return None


def main() -> None:
    """Punto de entrada principal."""
    args = parse_args()

    # Cargar configuracion
    config = load_agents_config()

    # Override con args de CLI
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if args.log_level:
        config.log_level = args.log_level

    # Configurar logging
    setup_logging(level=config.log_level, log_file=args.log_file)

    logger.info(f"{'=' * 60}")
    logger.info(f"{APP_NAME} v{APP_VERSION}")
    logger.info(f"{'=' * 60}")
    logger.info(f"Host: {config.host}:{config.port}")
    logger.info(f"Log level: {config.log_level}")
    logger.info(f"Max sesiones: {config.max_sessions}")
    logger.info(f"Personalidad: {config.personality}")
    logger.info(f"Idioma: {config.language}")
    logger.info(f"Streaming: {config.streaming_enabled}")
    logger.info(f"Tools: {config.tools_enabled}")
    logger.info(f"Memory: {config.memory_enabled}")

    # Cargar motor DAG Core si se solicita
    orchestrator = None
    if args.with_engine:
        orchestrator = load_zenic_engine(auth=args.auth)

    # Crear aplicacion
    from src.core.conversational.server.app import create_app
    app = create_app(config=config, orchestrator=orchestrator)

    # Iniciar servidor
    import uvicorn
    logger.info(f"Iniciando servidor en {config.host}:{config.port}")
    logger.info(f"Endpoints: /v1/chat, /v1/sessions, /ws/chat, /health")

    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower(),
        access_log=config.debug,
    )


if __name__ == "__main__":
    main()
