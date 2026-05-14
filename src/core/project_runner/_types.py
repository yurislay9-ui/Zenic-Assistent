"""
ProjectRunner — Types and Constants

RunResult dataclass and timeout constants.
"""

from dataclasses import dataclass, field
from typing import List, Optional


# Default timeout for operations
INSTALL_TIMEOUT = 120  # seconds
START_TIMEOUT = 15     # seconds
HEALTH_TIMEOUT = 5     # seconds


@dataclass
class RunResult:
    """Result of a project run attempt."""
    success: bool = False
    project_name: str = ""
    project_dir: str = ""
    venv_dir: str = ""
    port: int = 0
    pid: Optional[int] = None
    health_ok: bool = False
    installed_deps: List[str] = field(default_factory=list)
    failed_deps: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    startup_time_s: float = 0.0
