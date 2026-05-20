"""
ZENIC-AGENTS - Diff Preview Formatter

Formatting utilities for rendering DiffResult objects as text or JSON.
"""

from __future__ import annotations

import json
from typing import Any, List

from ._types import DiffEntry, DiffResult


# ──────────────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────────────

def truncate(value: Any, max_len: int = 50) -> str:
    """Truncate a value representation for display."""
    s = str(value)
    if len(s) > max_len:
        return s[:max_len - 3] + "..."
    return s


# ──────────────────────────────────────────────────────────────
#  FORMATTING
# ──────────────────────────────────────────────────────────────

def format_diff(
    diff_result: DiffResult,
    format: str = "text",
) -> str:
    """Format a DiffResult as text or JSON.

    Args:
        diff_result: The diff result to format.
        format: Output format — ``"text"`` (default) or ``"json"``.

    Returns:
        Formatted string representation.
    """
    if format.lower() == "json":
        return json.dumps(diff_result.to_dict(), indent=2, default=str)

    # Text format
    lines: List[str] = []
    lines.append(f"Diff Preview: {diff_result.action_type}")
    lines.append(f"Risk: {diff_result.estimated_risk}")
    lines.append(f"Summary: {diff_result.summary}")
    lines.append("")

    if diff_result.affected_tables:
        lines.append(f"Affected tables: {', '.join(diff_result.affected_tables)}")
    if diff_result.affected_files:
        lines.append(f"Affected files: {', '.join(diff_result.affected_files)}")

    if diff_result.diffs:
        lines.append("")
        lines.append("Changes:")
        for d in diff_result.diffs:
            change_symbol = {
                "added": "+",
                "modified": "~",
                "removed": "-",
            }.get(d.change_type, "?")
            lines.append(
                f"  [{change_symbol}] {d.field_path}: "
                f"{truncate(d.old_value)} → {truncate(d.new_value)}"
            )

    return "\n".join(lines)
