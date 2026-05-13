"""
ZENIC-AGENTS — Single Source of Truth for System-Wide Constants.

This module is the ONLY place where these constants are defined.
All other modules MUST import from here — never redefine locally.

Constants defined:
  - VALID_INTENT_OPERATIONS: frozenset of valid intent operations (CREATE, REFACTOR, etc.)
  - VALID_INTENT_GOALS: frozenset of valid intent goals (BUG_FIX, FEATURE_ADD, etc.)
  - VALID_INVENTORY_OPERATIONS: frozenset of valid inventory ops (add, remove, etc.)
  - VALID_LANGUAGES: frozenset of supported programming languages
  - EXT_LANG_MAP: file extension → language mapping
  - FENCE_LANG_MAP: markdown fence label → language mapping
"""

# ────────────────────────────── Intent Operations ──────────────────────────────

VALID_INTENT_OPERATIONS: frozenset[str] = frozenset({
    "CREATE", "REFACTOR", "DELETE", "SEARCH",
    "ANALYZE", "EXPLAIN", "DEBUG", "OPTIMIZE",
})

VALID_INTENT_GOALS: frozenset[str] = frozenset({
    "COMPLEXITY_REDUCTION", "MODERN_PATTERN", "BUG_FIX",
    "FEATURE_ADD", "SECURITY_HARDEN", "PERFORMANCE", "READABILITY",
    "AUTOMATION",
})


# ────────────────────────────── Inventory Operations ──────────────────────────────

VALID_INVENTORY_OPERATIONS: frozenset[str] = frozenset({
    "add", "remove", "set", "adjust",
})


# ────────────────────────────── Languages ──────────────────────────────

VALID_LANGUAGES: frozenset[str] = frozenset({
    "python", "kotlin", "go", "javascript", "typescript",
    "java", "rust", "c", "cpp", "ruby", "swift", "scala",
})

EXT_LANG_MAP: dict[str, str] = {
    ".py": "python", ".kt": "kotlin", ".go": "go",
    ".js": "javascript", ".ts": "typescript", ".java": "java",
    ".rs": "rust", ".rb": "ruby", ".cpp": "cpp", ".c": "c",
    ".h": "c", ".hpp": "cpp", ".swift": "swift", ".scala": "scala",
}

FENCE_LANG_MAP: dict[str, str] = {
    "python": "python", "py": "python",
    "kotlin": "kotlin", "kt": "kotlin",
    "go": "go", "golang": "go",
    "javascript": "javascript", "js": "javascript",
    "typescript": "typescript", "ts": "typescript",
    "java": "java",
    "rust": "rust", "rs": "rust",
    "ruby": "ruby", "rb": "ruby",
    "c": "c", "cpp": "cpp", "c++": "cpp",
}
