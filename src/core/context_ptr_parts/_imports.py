"""
Shared imports, constants, and dataclasses for context_ptr_parts.
"""

import os
import re
import ast
import json
import hashlib
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# === Storage Root ===
CONTEXT_STORE_ROOT = os.path.join(
    os.path.expanduser("~"), ".zenic_agents", "context_store"
)


@dataclass
class FunctionSignature:
    """Firma vectorizada de una función/método."""
    name: str
    file_path: str
    line_start: int
    line_end: int
    params: List[str] = field(default_factory=list)
    return_type: str = ""
    docstring: str = ""
    complexity: int = 1
    calls: List[str] = field(default_factory=list)
    hash: str = ""

    def to_pointer(self) -> str:
        """Convierte la firma en un puntero compacto para el modelo."""
        params_str = ", ".join(self.params) if self.params else "()"
        ret = f" -> {self.return_type}" if self.return_type else ""
        return f"📍 {self.name}({params_str}){ret} @ L{self.line_start}-{self.line_end} [{self.file_path}]"
