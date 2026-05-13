"""
ZENIC-AGENTS - Resource Governor v16 (Termux/proot-distro)

Monitor y limitador de recursos para que el engine no chupe
todos los recursos del telefono.
"""

from .governor import ResourceGovernor
from .singleton import get_governor, init_governor
from .utils import tune_gc_for_arm, set_process_priority_low, limit_open_files

__all__ = [
    "ResourceGovernor", "get_governor", "init_governor",
    "tune_gc_for_arm", "set_process_priority_low", "limit_open_files",
]
