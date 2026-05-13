"""Shared imports and constants for model_mgr_parts."""

import os
import time
import threading
import logging
import platform
from typing import Optional, Dict, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# === Configuration from environment ===
IDLE_TIMEOUT_S = int(os.environ.get("ZENIC_MODEL_IDLE_TIMEOUT", "300"))  # 5 min default
RAM_BUDGET_MB = int(os.environ.get("ZENIC_RAM_BUDGET_MB", "4096"))  # Max RAM for models (matches governor 4096MB)
ENABLE_AUTO_UNLOAD = os.environ.get("ZENIC_AUTO_UNLOAD", "1") == "1"
ENABLE_LAZY_LOAD = os.environ.get("ZENIC_LAZY_LOAD", "1") == "1"
