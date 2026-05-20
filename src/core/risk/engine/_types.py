"""Types and constants for engine."""

from __future__ import annotations
import logging
import threading
from ..types import RiskLevel, BlastRadiusReport, RiskPropagationReport, CriticalPathReport, CompositeRiskReport

try:
    from ...native._risk import calculate_blast_radius, propagate_risks, find_critical_path, multi_node_blast_radius
    HAS_NATIVE = True
except ImportError:
    HAS_NATIVE = False

logger = logging.getLogger("zenic_agents.core.risk.engine")
