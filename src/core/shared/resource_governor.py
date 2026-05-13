"""
ZENIC-AGENTS - Resource Governor v16 (Termux/proot-distro)

Facade module — re-exports from governor_parts for backward compatibility.
"""

from .governor_parts import (
    ResourceGovernor,
    get_governor,
    init_governor,
    tune_gc_for_arm,
    set_process_priority_low,
    limit_open_files,
)

__all__ = [
    "ResourceGovernor",
    "get_governor",
    "init_governor",
    "tune_gc_for_arm",
    "set_process_priority_low",
    "limit_open_files",
]
