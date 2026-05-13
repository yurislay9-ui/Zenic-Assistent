"""Utility functions for GC tuning, process priority, and file limits."""

import os
import gc
import logging

from ._imports import resource

logger = logging.getLogger(__name__)


def tune_gc_for_arm():
    """
    Ajusta los thresholds del GC para ARM donde la memoria
    es mas limitada y el GC puede ser mas costoso.

    Python default: (700, 10, 10) - muy agresivo para telefono
    Nuestro tuning: (1000, 15, 15) - menos frecuente pero mas efectivo
    """
    thresholds = gc.get_threshold()
    new_thresholds = (1000, 15, 15)

    if thresholds != new_thresholds:
        gc.set_threshold(*new_thresholds)
        logger.info(
            "GC tuned for ARM: %s -> %s",
            thresholds, new_thresholds
        )

    # Habilitar DEBUG para detectar ciclos de referencia
    # Solo en modo debug, no en produccion
    if os.environ.get('ZENIC_DEBUG_GC'):
        gc.set_debug(gc.DEBUG_STATS)


def set_process_priority_low():
    """
    Baja la prioridad del proceso para que el telefono
    siga siendo responsivo mientras el engine trabaja.

    En proot-distro Debian: usa os.nice()
    En Termux nativo: usa os.nice() si tiene permisos
    """
    try:
        # Bajar prioridad (nice +10 = menor prioridad)
        os.nice(10)
        logger.info("Process priority lowered (nice +10)")
    except (PermissionError, AttributeError):
        logger.debug("Cannot lower process priority - running at default")


def limit_open_files(max_files=256):
    """
    Limita el numero de archivos abiertos para no agotar
    los file descriptors del sistema en Android.

    Cada SQLite connections usa un fd. Con 4 DBs + conexiones
    concurrentes, 256 es mas que suficiente.
    """
    if resource is not None:
        try:
            soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
            if soft > max_files:
                resource.setrlimit(resource.RLIMIT_NOFILE, (max_files, hard))
                logger.info("Open files limit: %d -> %d", soft, max_files)
        except (ValueError, AttributeError, OSError):
            pass
