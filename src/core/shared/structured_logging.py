"""
ZENIC-AGENTS v16 - Structured Logging

Formateador de logging estructurado (JSON) para observabilidad.
Compatible con Termux/ARM, sin dependencias externas.

Features:
- JSON structured output for machine parsing
- Request tracing with request_id
- Pipeline level tracking (L1-L8)
- Performance metrics in every log entry
- Graceful fallback to plain text if JSON fails
"""

import json
import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Optional

__all__ = ["StructuredFormatter", "PlainFormatter", "setup_logging", "log_pipeline_step"]


class StructuredFormatter(logging.Formatter):
    """
    Formateador de logging que produce JSON estructurado.

    Cada log entry incluye:
    - timestamp: ISO 8601 UTC
    - level: log level (INFO, WARNING, etc.)
    - logger: nombre del logger
    - message: mensaje principal
    - plus any extra fields passed via logging extras
    """

    def __init__(self, service_name="zenic-agents"):
        super().__init__()
        self.service_name = service_name

    def format(self, record):
        try:
            log_entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "service": self.service_name,
            }

            # Agregar campos extra si existen
            extra_fields = [
                "request_id", "pipeline_level", "operation", "target",
                "route", "criticality", "solver_status", "mcts_sims",
                "processing_time_ms", "cache_hit", "status",
                "language", "ast_functions", "ast_classes",
                # Phase 5: trace correlation fields
                "trace_id", "span_id", "tenant_id", "user_id",
                "audit_event_id", "audit_event_type", "audit_severity",
            ]
            for field in extra_fields:
                value = getattr(record, field, None)
                if value is not None:
                    log_entry[field] = value

            # Agregar exception info si existe
            if record.exc_info and record.exc_info[0] is not None:
                log_entry["exception"] = {
                    "type": record.exc_info[0].__name__,
                    "message": str(record.exc_info[1]),
                    "traceback": traceback.format_exception(*record.exc_info),
                }

            return json.dumps(log_entry, ensure_ascii=False, default=str)

        except Exception as e:
            # Fallback a formato plano si JSON falla
            # Note: using print to stderr instead of logger to avoid recursion in formatter
            import sys
            print(f"StructuredFormatter: JSON formatting failed: {e}", file=sys.stderr)
            return super().format(record)


class PlainFormatter(logging.Formatter):
    """
    Formateador plano legible para desarrollo y Termux.
    Incluye timestamp, nivel, logger y mensaje con colores simples.
    """

    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def __init__(self, use_color=True):
        super().__init__()
        self.use_color = use_color

    def format(self, record):
        timestamp = datetime.now().strftime("%H:%M:%S")
        level = record.levelname
        logger_name = record.name.split('.')[-1]  # Solo el ultimo componente

        if self.use_color:
            color = self.COLORS.get(level, "")
            reset = self.RESET
        else:
            color = ""
            reset = ""

        # Formato base
        msg = f"{timestamp} {color}[{level:7s}]{reset} {logger_name}: {record.getMessage()}"

        # Agregar extra fields compactos
        extras = []
        for field in ["request_id", "pipeline_level", "processing_time_ms",
                      "route", "status", "solver_status",
                      # Phase 5: trace correlation
                      "trace_id", "span_id", "tenant_id"]:
            value = getattr(record, field, None)
            if value is not None:
                extras.append(f"{field}={value}")

        if extras:
            msg += f" | {' '.join(extras)}"

        # Agregar exception
        if record.exc_info and record.exc_info[0] is not None:
            msg += "\n" + "".join(traceback.format_exception(*record.exc_info))

        return msg


def setup_logging(level=logging.INFO, structured=False, service_name="zenic-agents"):
    """
    Configura el logging del sistema.

    Args:
        level: Nivel de logging (default INFO)
        structured: Si True, usa JSON structured logging.
                   Si False, usa formato plano legible (recomendado para Termux)
        service_name: Nombre del servicio para structured logging
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Only add our handler if not already present; avoid clearing handlers from other libraries
    has_our_handler = any(
        isinstance(h, logging.StreamHandler) and
        isinstance(getattr(h, 'formatter', None), (StructuredFormatter, PlainFormatter))
        for h in root_logger.handlers
    )
    if has_our_handler:
        return  # Already configured

    handler = logging.StreamHandler()

    if structured:
        handler.setFormatter(StructuredFormatter(service_name))
    else:
        # Detectar si tenemos terminal con color support
        import sys
        use_color = hasattr(sys.stderr, 'isatty') and sys.stderr.isatty()
        handler.setFormatter(PlainFormatter(use_color=use_color))

    root_logger.addHandler(handler)


def log_pipeline_step(
    logger_instance,
    level: int,
    message: str,
    pipeline_level: Optional[int] = None,
    request_id: Optional[str] = None,
    **kwargs,
):
    """
    Helper para logear con campos estructurados del pipeline.

    Args:
        logger_instance: Logger a usar
        level: Nivel de logging
        message: Mensaje descriptivo
        pipeline_level: Nivel del pipeline (1-8)
        request_id: ID de la peticion
        **kwargs: Campos extra (operation, target, route, etc.)
    """
    extra = {}
    if pipeline_level is not None:
        extra["pipeline_level"] = pipeline_level
    if request_id is not None:
        extra["request_id"] = request_id
    extra.update(kwargs)

    logger_instance.log(level, message, extra=extra)
