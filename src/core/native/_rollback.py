"""
native._rollback — Coordinated Rollback (A3) API functions.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List

from src.core.native._bindings import HAS_NATIVE

if HAS_NATIVE:
    from src.core.native._bindings import (
        _rust_snapshot_file,
        _rust_restore_file,
        _rust_verify_rollback_readiness,
        _rust_file_hash,
    )


def snapshot_file(source_path: str, backup_path: str) -> Dict[str, Any]:
    """Create a backup snapshot of a file with BLAKE3 checksum."""
    if HAS_NATIVE:
        return _rust_snapshot_file(source_path, backup_path)
    # Pure Python fallback
    src = Path(source_path)
    if not src.exists():
        return {"success": False, "source_path": source_path,
                "backup_path": backup_path,
                "error": f"Source file does not exist: {source_path}"}
    try:
        data = src.read_bytes()
        checksum = hashlib.sha256(data).hexdigest()
        bk = Path(backup_path)
        bk.parent.mkdir(parents=True, exist_ok=True)
        bk.write_bytes(data)
        return {"success": True, "source_path": source_path,
                "backup_path": backup_path, "checksum": checksum,
                "file_size": len(data)}
    except Exception as exc:
        return {"success": False, "source_path": source_path,
                "backup_path": backup_path, "error": str(exc)}


def restore_file(
    backup_path: str, target_path: str, expected_checksum: str,
) -> Dict[str, Any]:
    """Restore a file from a backup with checksum verification."""
    if HAS_NATIVE:
        return _rust_restore_file(backup_path, target_path, expected_checksum)
    # Pure Python fallback
    bk = Path(backup_path)
    if not bk.exists():
        return {"success": False, "backup_path": backup_path,
                "target_path": target_path, "checksum_verified": False,
                "error": f"Backup file does not exist: {backup_path}"}
    try:
        data = bk.read_bytes()
        actual_checksum = hashlib.sha256(data).hexdigest()
        if actual_checksum != expected_checksum:
            return {"success": False, "backup_path": backup_path,
                    "target_path": target_path, "checksum_verified": False,
                    "error": f"Checksum mismatch: expected {expected_checksum}, got {actual_checksum}"}
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return {"success": True, "backup_path": backup_path,
                "target_path": target_path, "checksum_verified": True,
                "bytes_restored": len(data)}
    except Exception as exc:
        return {"success": False, "backup_path": backup_path,
                "target_path": target_path, "checksum_verified": False,
                "error": str(exc)}


def verify_rollback_readiness(
    resources: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Verify that all resources needed for rollback are available."""
    if HAS_NATIVE:
        return _rust_verify_rollback_readiness(resources)
    # Pure Python fallback
    total = len(resources)
    verified = 0
    failed: List[Dict[str, Any]] = []

    for res in resources:
        rtype = res.get("resource_type", "")
        if rtype == "file":
            bp = res.get("backup_path", "")
            ec = res.get("expected_checksum", "")
            bk = Path(bp) if bp else None
            if bk is None or not bk.exists():
                failed.append({"resource_type": rtype, "backup_path": bp,
                               "reason": "Backup file does not exist"})
                continue
            try:
                data = bk.read_bytes()
                actual = hashlib.sha256(data).hexdigest()
                if ec and actual != ec:
                    failed.append({"resource_type": rtype, "backup_path": bp,
                                   "reason": f"Checksum mismatch: expected {ec}, got {actual}"})
                else:
                    verified += 1
            except Exception as exc:
                failed.append({"resource_type": rtype, "backup_path": bp,
                               "reason": str(exc)})
        else:
            verified += 1

    return {"all_verified": len(failed) == 0, "total_resources": total,
            "verified_count": verified, "failed": failed}


def file_hash(file_path: str) -> str:
    """Compute the BLAKE3/SHA-256 hash of a file."""
    if HAS_NATIVE:
        return _rust_file_hash(file_path)
    # Pure Python fallback
    data = Path(file_path).read_bytes()
    if not data:
        raise RuntimeError(f"File is empty: {file_path}")
    try:
        import blake3 as _blake3  # type: ignore[import-untyped]
        return _blake3.blake3(data).hexdigest()
    except ImportError:
        return hashlib.sha256(data).hexdigest()
