"""
Shared imports, types, and constants for dna_loader_parts.
"""

import os
import re
import ast
import logging
import threading
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger(__name__)

DNA_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates", "dna"
)


@dataclass
class LogicModule:
    """Módulo de función atómica reutilizable."""
    id: str
    domain: str
    description: str
    code_block: str
    dependencies: List[str] = field(default_factory=list)
    verification_rule: str = ""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)


@dataclass
class DomainRule:
    """Regla de negocio obligatoria por industria."""
    name: str
    display_name: str
    description: str
    mandatory_logic: List[str] = field(default_factory=list)
    ux_patterns: List[str] = field(default_factory=list)
    compliance_requirements: List[str] = field(default_factory=list)
    business_invariants: List[str] = field(default_factory=list)
    edge_cases: List[str] = field(default_factory=list)
    suggested_entities: List[str] = field(default_factory=list)
    notification_triggers: List[str] = field(default_factory=list)


@dataclass
class ValidationGate:
    """Regla de validación de calidad."""
    id: str
    category: str
    rule: str
    action: str
    severity: str = "warning"
    auto_fix: bool = False
    fix_strategy: str = ""
    pattern: str = ""
    applies_to: List[str] = field(default_factory=list)


@dataclass
class GlossaryEntry:
    """Transformación de jerga técnica a lenguaje corporativo."""
    from_term: str
    to_term: str
    context: str = ""
