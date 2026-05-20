"""Types and constants for conditional_branch."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from .chain_composer import ChainStep

logger = logging.getLogger(__name__)


@dataclass
class BranchCondition:
    """A single condition that maps to a target step."""

    expression: str = ""
    target_step_id: str = ""
    description: str = ""


@dataclass
class BranchRule:
    """A named collection of branch conditions with a default branch."""

    rule_id: str = ""
    name: str = ""
    conditions: list[BranchCondition] = field(default_factory=list)
    default_branch: str = ""
    priority: int = 0
    created_at: float = 0.0


# Token patterns for the expression parser
_TOKEN_RE = re.compile(
    r"""
    (?P<STRING>  '(?:[^'\\]|\\.)*' | "(?:[^"\\]|\\.)*" )  # quoted strings
    | (?P<NUMBER>  \d+(?:\.\d+)?)                           # numbers
    | (?P<BOOL>    True|False|None                           # boolean/none literals
    | (?P<IDENT>   [a-zA-Z_][\w.]*)                         # identifiers (allow dots)
    | (?P<OP>      ==|!=|>=|<=|>|<)                         # comparison operators
    | (?P<LPAREN>  \(                                       # left paren
    | (?P<RPAREN>  \)                                       # right paren
    | (?P<KEYWORD> and|or|not|contains|startswith|endswith|exists|not_empty  # keywords
    | (?P<WS>      \s+                                      # whitespace
    | (?P<MISMATCH>.)                                       # any other character
    """,
    re.VERBOSE,
)

_KEYWORDS = frozenset({
    "and", "or", "not",
    "contains", "startswith", "endswith", "exists", "not_empty",
    "True", "False", "None",
})
