"""
Shared imports and constants for template_parts sub-modules.
"""

import os
import json
import logging
import secrets as _secrets
from typing import Optional, Dict, Any, List, Set
from dataclasses import dataclass, field
from pathlib import Path

try:
    from jinja2 import Environment, FileSystemLoader, Template, TemplateError
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False

logger = logging.getLogger(__name__)

# Sentinel object for lazy-load failure
_LOAD_FAILED = object()

# Template Root
TEMPLATE_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "templates")


@dataclass
class TemplateBlock:
    """Bloque de codigo reutilizable y pre-construido."""
    name: str
    category: str  # business_logic, integrations, auth, data
    description: str
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    template_path: str = ""


@dataclass
class CompositionPlan:
    """Plan de composicion de templates generado por la AI."""
    base_template: str = "apps/base"
    app_template: str = ""
    blocks: List[str] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    entities: List[Dict[str, Any]] = field(default_factory=list)
