"""ZENIC-AGENTS - Impact Preview Engine: File Preview Logic

Simulates the effects of file operations WITHOUT executing them.
All operations are strictly READ-ONLY — this module never modifies data.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ._types import (
    ImpactRiskLevel,
    FileImpactPreview,
)


def _safe_resolve(path: str, base_dir: str) -> Optional[str]:
    """Safely resolve a file path within base_dir.

    Returns None if path is empty or would escape base_dir.
    """
    if not path:
        return None
    try:
        base = os.path.realpath(base_dir) if base_dir else os.path.realpath(os.getcwd())
        if os.path.isabs(path):
            resolved = os.path.realpath(path)
            if resolved.startswith(base + os.sep) or resolved == base:
                return resolved
            return None  # Path traversal
        resolved = os.path.realpath(os.path.join(base, path))
        if resolved.startswith(base + os.sep) or resolved == base:
            return resolved
        return None  # Path traversal
    except Exception:
        return None


def preview_file_operation(config: Dict[str, Any]) -> FileImpactPreview:
    """Preview a file operation WITHOUT executing it.

    Shows files affected, sizes, whether they exist,
    and whether the operation would overwrite or delete.

    Args:
        config: File operation config with keys like operation, source, destination, base_dir.

    Returns:
        A FileImpactPreview with the estimated impact.
    """
    operation = str(config.get("operation", "read")).lower()
    base_dir = config.get("base_dir", os.getcwd())
    source = str(config.get("source", ""))
    destination = str(config.get("destination", ""))

    preview = FileImpactPreview(
        operation=operation,
        source=source,
        destination=destination,
        risk_level=ImpactRiskLevel.NONE,
        risk_score=0.0,
        summary=f"File {operation}",
        reversible=True,
    )

    # Safely resolve paths
    safe_source = _safe_resolve(source, base_dir)
    safe_dest = _safe_resolve(destination, base_dir)

    # Inspect source
    if safe_source:
        preview.source_exists = os.path.exists(safe_source)
        if preview.source_exists:
            try:
                if os.path.isfile(safe_source):
                    preview.source_size = os.path.getsize(safe_source)
                    preview.source_is_dir = False
                elif os.path.isdir(safe_source):
                    preview.source_is_dir = True
                    # Count files in directory
                    try:
                        preview.source_size = sum(
                            os.path.getsize(os.path.join(safe_source, f))
                            for f in os.listdir(safe_source)
                            if os.path.isfile(os.path.join(safe_source, f))
                        )
                    except OSError:
                        preview.source_size = 0
            except OSError:
                preview.source_size = 0

    # Inspect destination
    if safe_dest:
        preview.destination_exists = os.path.exists(safe_dest)
        if preview.destination_exists:
            try:
                if os.path.isfile(safe_dest):
                    preview.destination_size = os.path.getsize(safe_dest)
                    preview.destination_is_dir = False
                elif os.path.isdir(safe_dest):
                    preview.destination_is_dir = True
            except OSError:
                preview.destination_size = 0

    # Compute operation-specific impact
    if operation == "read":
        preview.read_only = True
        preview.reversible = True
        preview.summary = f"Read file: {source}"
        if not preview.source_exists:
            preview.warnings.append(f"Source file does not exist: {source}")
            preview.risk_level = ImpactRiskLevel.LOW
            preview.risk_score = 0.1

    elif operation == "write":
        preview.read_only = False
        preview.would_create = not preview.destination_exists
        preview.would_overwrite = preview.destination_exists
        preview.reversible = False if preview.would_overwrite else True
        preview.summary = (
            f"Overwrite file: {destination}" if preview.would_overwrite
            else f"Create file: {destination}"
        )
        if preview.would_overwrite:
            preview.warnings.append(
                f"Would overwrite existing file ({preview.destination_size} bytes): {destination}"
            )
            preview.risk_level = ImpactRiskLevel.MEDIUM
            preview.risk_score = 0.4
        else:
            preview.risk_level = ImpactRiskLevel.LOW
            preview.risk_score = 0.1

    elif operation == "append":
        preview.read_only = False
        preview.reversible = False
        preview.summary = f"Append to file: {destination or source}"
        if not preview.source_exists and not preview.destination_exists:
            preview.would_create = True
            preview.summary = f"Append (creates new file): {destination or source}"
        preview.risk_level = ImpactRiskLevel.LOW
        preview.risk_score = 0.2

    elif operation == "delete":
        preview.read_only = False
        preview.would_delete = preview.source_exists
        preview.reversible = False
        preview.summary = (
            f"Delete: {source}" if preview.source_exists
            else f"Delete (not found): {source}"
        )
        if preview.source_exists:
            size_str = f" ({preview.source_size} bytes)" if not preview.source_is_dir else " (directory)"
            preview.warnings.append(
                f"Would permanently delete{size_str}: {source}"
            )
            preview.risk_level = ImpactRiskLevel.HIGH
            preview.risk_score = 0.8
        else:
            preview.warnings.append(f"Source does not exist: {source}")
            preview.risk_level = ImpactRiskLevel.LOW
            preview.risk_score = 0.1

    elif operation == "copy":
        preview.read_only = False
        preview.would_overwrite = preview.destination_exists
        preview.would_create = not preview.destination_exists
        preview.reversible = True
        preview.summary = f"Copy: {source} \u2192 {destination}"
        if preview.would_overwrite:
            preview.warnings.append(
                f"Would overwrite existing destination: {destination}"
            )
            preview.risk_level = ImpactRiskLevel.MEDIUM
            preview.risk_score = 0.3
        else:
            preview.risk_level = ImpactRiskLevel.LOW
            preview.risk_score = 0.1

    elif operation == "move":
        preview.read_only = False
        preview.would_delete = preview.source_exists
        preview.would_overwrite = preview.destination_exists
        preview.would_create = not preview.destination_exists
        preview.reversible = False
        preview.summary = f"Move: {source} \u2192 {destination}"
        if preview.destination_exists:
            preview.warnings.append(
                f"Would overwrite destination: {destination}"
            )
        if preview.source_exists:
            preview.warnings.append(
                f"Source will be removed after move: {source}"
            )
        preview.risk_level = ImpactRiskLevel.MEDIUM
        preview.risk_score = 0.5

    else:
        preview.summary = f"File operation: {operation}"
        preview.risk_level = ImpactRiskLevel.LOW
        preview.risk_score = 0.1

    return preview
