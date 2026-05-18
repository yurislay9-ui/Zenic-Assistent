"""Types and constants for experiment_runner."""

from __future__ import annotations
import logging
from pathlib import Path

from ..types import ChaosExperiment, FaultInjection, FaultType, ChaosExperimentState

logger = logging.getLogger("zenic_agents.core.chaos.experiment_runner")

DB_DIR = Path.home() / ".zenic_agents" / "db"

DB_PATH = DB_DIR / "chaos.sqlite"
