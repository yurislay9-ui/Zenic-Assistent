"""
Shared imports, constants, and patterns for validation_agent_parts.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import ValidationInput, ValidationOutput, ValidationIssue
from src.core.agents.prompts import AgentPrompts, PromptBuilder

logger = logging.getLogger(__name__)

# Security vulnerability patterns
SECURITY_PATTERNS = [
    (r'\beval\s*\(', "dangerous_eval", "Use of eval() is a security risk", "error"),
    (r'\bexec\s*\(', "dangerous_exec", "Use of exec() is a security risk", "error"),
    (r'\bos\.system\s*\(', "command_injection", "os.system() allows command injection", "error"),
    (r'\bsubprocess\.call\s*\([^)]*shell\s*=\s*True', "shell_injection",
     "subprocess with shell=True allows injection", "error"),
    (r'\binput\s*\(', "unvalidated_input", "input() without validation", "warning"),
    (r'\bpickle\.loads?\s*\(', "pickle_deserialization", "Pickle deserialization is unsafe", "error"),
    (r'\byaml\.load\s*\([^)]*\)', "yaml_unsafe_load", "Use yaml.safe_load() instead", "warning"),
    (r'\bhashlib\.md5\b', "weak_hash_md5", "MD5 is cryptographically broken", "warning"),
    (r'\bhashlib\.sha1\b', "weak_hash_sha1", "SHA-1 is cryptographically weak", "warning"),
    (r'SELECT\s+\*\s+FROM', "select_star", "SELECT * may expose sensitive data", "info"),
    (r'\.format\s*\(', "format_injection", "str.format() can be exploited if user-controlled", "warning"),
    (r'%[sdfi]', "old_style_format", "Old-style string formatting (%s)", "info"),
]

# Code quality patterns
QUALITY_PATTERNS = [
    (r'except\s*:', "bare_except", "Bare except catches all exceptions including SystemExit",
     "warning"),
    (r'except\s+Exception\s*:', "broad_exception", "Catching Exception is very broad", "info"),
    (r'pass\s*$', "empty_block", "Empty block (pass) - add implementation or comment",
     "info"),
    (r'TODO|FIXME|HACK|XXX', "todo_comment", "Unresolved TODO/FIXME comment", "info"),
    (r'print\s*\(', "print_statement", "print() found - consider using logging", "info"),
]

# Chain validation rules
CHAIN_COMPATIBILITY_RULES = {
    ("data", "validation"): "good",
    ("validation", "data"): "good",
    ("data", "business_logic"): "good",
    ("validation", "business_logic"): "warning",
    ("business_logic", "validation"): "warning",
}
