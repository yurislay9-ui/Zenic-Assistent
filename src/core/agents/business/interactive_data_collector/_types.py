"""
Data types for InteractiveDataCollector — session and result objects.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional


class CompletionSession:
    """Python fallback session for template completion."""

    __slots__ = ("session_id", "niche_id", "round_count", "created_at", "answers")

    def __init__(self, niche_id: str) -> None:
        self.session_id = f"py-{niche_id}-{uuid.uuid4().hex[:8]}"
        self.niche_id = niche_id
        self.round_count = 0
        self.created_at = time.time()
        self.answers: Dict[str, str] = {}


class InteractiveCollectionResult:
    """Result of an interactive data collection operation."""

    __slots__ = (
        "session_id",
        "niche_id",
        "questions",
        "answers_applied",
        "answers_rejected",
        "still_missing",
        "completion_pct",
        "is_complete",
        "round_number",
        "source",
    )

    def __init__(
        self,
        session_id: str = "",
        niche_id: str = "",
        questions: Optional[List[Dict[str, Any]]] = None,
        answers_applied: int = 0,
        answers_rejected: int = 0,
        still_missing: int = 0,
        completion_pct: float = 0.0,
        is_complete: bool = False,
        round_number: int = 0,
        source: str = "deterministic",
    ) -> None:
        self.session_id = session_id
        self.niche_id = niche_id
        self.questions = questions or []
        self.answers_applied = answers_applied
        self.answers_rejected = answers_rejected
        self.still_missing = still_missing
        self.completion_pct = completion_pct
        self.is_complete = is_complete
        self.round_number = round_number
        self.source = source
