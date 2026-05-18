"""
ZENIC-AGENTS - DB Journal Data Models

Dataclasses used by the DB Transaction Journal system.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass
class JournalEntry:
    """A single journal record capturing state before a write operation.

    Attributes:
        journal_id: Unique identifier for this journal entry.
        db_path: Path to the SQLite database that was modified.
        operation: The SQL operation type (INSERT, UPDATE, DELETE).
        query: The SQL query that was (or will be) executed.
        params: The query parameters.
        before_data: JSON string of row state BEFORE the write.
            For DELETE/UPDATE this is a list of dicts captured via SELECT.
            For INSERT this is ``"[]"`` (no prior data existed).
        after_data: JSON string of row state AFTER the write (populated by
            ``journal_after``).  ``"[]"`` until ``journal_after`` is called.
        affected_rows: Number of rows affected by the write.
        lastrowid: The ``lastrowid`` from the cursor (for INSERT rollback).
        tenant_id: Tenant that owns this journal entry.
        created_at: Unix timestamp when the journal entry was created.
        rolled_back: Whether this entry has already been rolled back.
    """

    journal_id: str = ""
    db_path: str = ""
    operation: str = ""
    query: str = ""
    params: List[Any] = field(default_factory=list)
    before_data: str = "[]"
    after_data: str = "[]"
    affected_rows: int = 0
    lastrowid: Optional[int] = None
    tenant_id: str = ""
    created_at: float = 0.0
    rolled_back: bool = False

    def __post_init__(self) -> None:
        if not self.journal_id:
            self.journal_id = uuid.uuid4().hex
        if not self.created_at:
            self.created_at = time.time()


@dataclass
class RollbackResult:
    """Result of a rollback operation.

    Attributes:
        success: Whether the rollback completed without errors.
        journal_id: The journal entry that was rolled back.
        operation: The original operation type that was reversed.
        rows_restored: Number of rows restored by the rollback.
        errors: List of error messages encountered during rollback.
    """

    success: bool = False
    journal_id: str = ""
    operation: str = ""
    rows_restored: int = 0
    errors: List[str] = field(default_factory=list)
