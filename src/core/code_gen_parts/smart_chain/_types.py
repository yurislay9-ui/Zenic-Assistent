"""
SmartPromptChain — Fragmented generation for small LLMs (Qwen3-0.6B).

Problem: Qwen3-0.6B (600 M params) cannot generate a 200-line file in one call.
Solution: Break generation into atomic steps of 20-50 lines each, with
context carry-forward between steps. Each step is manageable for the model.

Architecture:
  1. plan_steps() — decompose task into atomic generation steps
  2. execute_step() — generate one fragment with context from previous steps
  3. assemble_fragments() — concatenate validated fragments into final file
  4. auto_repair() — if a fragment fails, retry with error context

M2 Enhancement: Template fallbacks now generate REAL functional code
(CRUD services, auth modules, integration clients) instead of minimal stubs.
When the LLM is unavailable or produces garbage, the template fallbacks
produce complete, working Python modules.
"""

import re
import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("zenic_agents.code_gen_parts.smart_chain")

# Maximum lines per step — Qwen3-0.6B reliable output range
MAX_LINES_PER_STEP = 40
MAX_REPAIR_ATTEMPTS = 3


@dataclass
class GenerationStep:
    """A single atomic generation step."""
    step_id: int
    step_type: str  # "schema" | "imports" | "class_def" | "method" | "tests"
    description: str
    prompt: str
    context: str = ""  # Code from previous steps
    generated: str = ""
    validated: bool = False
    attempts: int = 0


@dataclass
class ChainResult:
    """Result of a SmartPromptChain execution."""
    success: bool
    code: str = ""
    steps_total: int = 0
    steps_completed: int = 0
    steps_failed: int = 0
    repair_count: int = 0
    fragments: List[str] = field(default_factory=list)

