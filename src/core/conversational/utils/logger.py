"""
Logger del Asistente.

Configura logging estructurado con formato consistente,
rotacion de archivos y niveles configurables.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

from ..config.constants import LOG_FORMAT, LOG_LEVEL_DEFAULT, LOG_MAX_BYTES, LOG_BACKUP_COUNT


def setup_logging(
    level: str = LOG_LEVEL_DEFAULT,
    log_file: Optional[str] = None,
) -> None:
    """
    Configura el logging global del asistente.

    Args:
        level: Nivel de log (DEBUG, INFO, WARNING, ERROR).
        log_file: Archivo de log opcional con rotacion.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Handler de consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))

    # Handler de archivo (opcional)
    handlers: list[logging.Handler] = [console_handler]
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
        handlers.append(file_handler)

    # Configurar root logger
    root_logger = logging.getLogger("zenic_agents.conversational")
    root_logger.setLevel(log_level)
    root_logger.handlers.clear()
    for handler in handlers:
        root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger con el prefijo del asistente.

    Args:
        name: Nombre del modulo (se agrega como sufijo).

    Returns:
        Logger configurado.
    """
    return logging.getLogger(f"zenic_agents.conversational.{name}")
