"""Types and constants for inter_workflow."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(os.path.expanduser("~"), ".zenic_agents", "db")

_DB_PATH = os.path.join(_DB_DIR, "inter_workflow.sqlite")


@dataclass
class FieldMapping:
    """A single source→target field mapping specification."""

    source_path: str = ""  # e.g. "output.invoice_id"
    target_path: str = ""  # e.g. "input.invoice_id"


@dataclass
class HandoffRule:
    """A rule that wires a source chain's output to a target chain's input."""

    handoff_id: str = ""
    source_chain_id: str = ""
    target_chain_id: str = ""
    field_mapping: dict[str, str] = field(default_factory=dict)
    condition: str = ""
    enabled: bool = True
    created_at: float = 0.0


@dataclass
class HandoffResult:
    """Result of executing a single handoff."""

    handoff_id: str = ""
    success: bool = False
    target_chain_id: str = ""
    mapped_data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


_ALLOWED_NAMES: set[str] = {
    "abs", "len", "max", "min", "round", "int", "float", "str", "bool",
    "list", "dict", "set", "tuple", "sorted", "sum", "any", "all",
    "True", "False", "None",
}

_COMPARISON_OPS = re.compile(
    r"(==|!=|>=|<=|>|<)"
)

_KEYWORDS = frozenset({
    "and", "or", "not", "in", "is",
    "True", "False", "None",
    "contains", "startswith", "endswith", "exists", "not_empty",
})
