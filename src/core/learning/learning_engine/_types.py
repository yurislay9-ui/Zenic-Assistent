"""Types and constants for learning_engine."""

from __future__ import annotations
import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from .outcome_tracker import ActionOutcome, OutcomeStatus, get_outcome_tracker

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".zenic_agents" / "db"

DB_PATH = DB_DIR / "learning.sqlite"

class LearningStrategy(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"



@dataclass
class LearningInsight:
    id: str = ""
    insight_type: str = ""
    pattern: str = ""
    recommendation: str = ""
    confidence: float = 0.0
    supporting_outcomes: List[str] = field(default_factory=list)
    created_at: str = ""
    applied: bool = False


