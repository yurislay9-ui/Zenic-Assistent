"""Re-exports for autonomy package."""

from ._types import *
from ._helpers import *
from ._mixin_core import *

import json
import logging
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

_autonomy_config_instance: Optional[AutonomyConfigManager] = None
_autonomy_config_lock = threading.Lock()
def get_autonomy_config(db_path: str = "autonomy_config.sqlite") -> AutonomyConfigManager:
    """Get or create the global AutonomyConfigManager instance.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        The singleton AutonomyConfigManager instance.
    """
    global _autonomy_config_instance
    with _autonomy_config_lock:
        if _autonomy_config_instance is None:
            _autonomy_config_instance = AutonomyConfigManager(db_path=db_path)
        return _autonomy_config_instance


def reset_autonomy_config() -> None:
    """Reset the global AutonomyConfigManager instance (for testing)."""
    global _autonomy_config_instance
    with _autonomy_config_lock:
        _autonomy_config_instance = None



__all__ = [
    "AutonomyLevel",
    "AutonomyConfig",
    "AutonomyConfigManager",
    "get_autonomy_config",
    "reset_autonomy_config",
]