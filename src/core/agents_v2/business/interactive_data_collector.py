"""
A51 InteractiveDataCollector — SINGLE RESPONSIBILITY: Interactive dialogue for missing template fields.

Wraps the Rust-compiled completer module (Phase 6.C) as a proper
v2 agent in the Business layer. Provides the interactive Q&A loop
that asks users for missing required fields in niche templates.

Deterministic: All logic delegates to Rust completer functions.
No AI. All validation is pattern-based and type-checked.

Python fallback: When Rust extension is not available, provides
a working deterministic implementation that:
  - Starts sessions with generated session IDs
  - Generates questions from template structure
  - Validates answers by field type
  - Tracks completion progress
  - Supports batch answer submission
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Dict, List, Optional

from ..resilience.base_agent import BaseAgent


# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

MAX_ANSWER_LENGTH = 10000
MAX_QUESTIONS_PER_ROUND = 10
MAX_ROUNDS = 20

# Field type validators (deterministic, no AI)
_FIELD_VALIDATORS = {
    "text": lambda v: len(v) > 0,
    "string": lambda v: len(v) > 0,
    "email": lambda v: bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v)),
    "url": lambda v: bool(re.match(r"^https?://[^\s]+$", v)),
    "number": lambda v: v.replace(".", "", 1).replace("-", "", 1).isdigit(),
    "integer": lambda v: v.lstrip("-").isdigit(),
    "boolean": lambda v: v.lower() in ("true", "false", "yes", "no", "1", "0"),
    "enum": lambda v: len(v) > 0,  # validated against variants separately
    "date": lambda v: bool(re.match(r"^\d{4}-\d{2}-\d{2}$", v)),
    "phone": lambda v: bool(re.match(r"^\+?[\d\s\-\(\)]{7,}$", v)),
    "currency": lambda v: bool(re.match(r"^[A-Z]{3}$", v)) or v.replace(".", "", 1).isdigit(),
    "json": lambda v: v.startswith("{") or v.startswith("[") or v.startswith('"'),
}

# Field type suggestions
_FIELD_SUGGESTIONS = {
    "business_name": ["Mi Empresa S.A.", "Startup Inc.", "Consultora ABC"],
    "business_email": ["contacto@miempresa.com", "info@startup.com"],
    "business_phone": ["+1 555 0100", "+34 91 123 4567"],
    "currency": ["USD", "EUR", "MXN", "COP", "ARS", "CLP"],
    "country": ["US", "ES", "MX", "CO", "AR", "CL"],
    "language": ["es", "en", "pt", "fr"],
    "timezone": ["America/Havana", "Europe/Madrid", "America/Mexico_City", "America/Bogota"],
    "website": ["https://miempresa.com", "https://startup.io"],
    "industry": ["technology", "healthcare", "finance", "education", "retail"],
    "team_size": ["1-5", "6-20", "21-50", "51-200", "200+"],
}


# ──────────────────────────────────────────────────────────────
# PYTHON FALLBACK SESSION
# ──────────────────────────────────────────────────────────────

class _CompletionSession:
    """Python fallback session for template completion."""

    __slots__ = ("session_id", "niche_id", "round_count", "created_at", "answers")

    def __init__(self, niche_id: str) -> None:
        self.session_id = f"py-{niche_id}-{uuid.uuid4().hex[:8]}"
        self.niche_id = niche_id
        self.round_count = 0
        self.created_at = time.time()
        self.answers: Dict[str, str] = {}


# ──────────────────────────────────────────────────────────────
# RESULT TYPE
# ──────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────
# A51 AGENT
# ──────────────────────────────────────────────────────────────

class InteractiveDataCollector(BaseAgent[InteractiveCollectionResult]):
    """
    A51: Interactive dialogue for missing template fields.

    Single Responsibility: Ask user for missing required fields ONLY.
    Method: Delegates to Rust completer functions via _zenic_native.
    Fallback: Full deterministic Python implementation with:
      - Session management
      - Question generation from template structure
      - Type-based answer validation
      - Completion progress tracking
      - Batch answer submission

    This agent wraps the Rust completer module which provides:
    - completer_start_session: Create a completion session
    - completer_get_questions: Get questions for missing fields
    - completer_submit_answer: Submit a single answer
    - completer_submit_answers: Submit batch answers
    - completer_validate_answer: Validate an answer before submission
    - completer_get_progress: Get completion progress
    - completer_is_complete: Check if all required fields filled
    - completer_finalize: Produce final YAML template
    - completer_get_field_suggestions: Get suggestions for a field
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A51_InteractiveDataCollector", **kwargs)
        self._native = None
        self._python_sessions: Dict[str, _CompletionSession] = {}

    def _get_native(self):
        """Lazy-load the zenic Rust extension (if available)."""
        if self._native is None:
            try:
                # Import _zenic_native directly — the Rust PyO3 extension module
                import _zenic_native as _native_mod  # type: ignore[import-not-found]
                self._native = {
                    "completer_start_session": _native_mod.completer_start_session,
                    "completer_ingest_documents": _native_mod.completer_ingest_documents,
                    "completer_get_questions": _native_mod.completer_get_questions,
                    "completer_submit_answer": _native_mod.completer_submit_answer,
                    "completer_submit_answers": _native_mod.completer_submit_answers,
                    "completer_validate_answer": _native_mod.completer_validate_answer,
                    "completer_get_progress": _native_mod.completer_get_progress,
                    "completer_is_complete": _native_mod.completer_is_complete,
                    "completer_finalize": _native_mod.completer_finalize,
                    "completer_get_field_suggestions": _native_mod.completer_get_field_suggestions,
                }
            except (ImportError, AttributeError):
                self._native = None
        return self._native

    def execute(self, input_data: Any) -> InteractiveCollectionResult:
        """
        Execute interactive data collection.

        Input (dict with keys):
            - action: str — one of "start", "get_questions", "submit_answer",
              "submit_answers", "validate", "progress", "is_complete", "finalize",
              "suggestions"
            - session: CompletionSession (for non-start actions)
            - template_dict: dict (for non-start actions)
            - niche_id: str (for "start" action)
            - field_name: str (for "submit_answer", "suggestions")
            - value: str (for "submit_answer", "validate")
            - answers: dict (for "submit_answers")
            - field_type: str (for "validate", "suggestions")

        Output: InteractiveCollectionResult with relevant data.
        """
        if not isinstance(input_data, dict):
            data = input_data.data if hasattr(input_data, "data") else {}
        else:
            data = input_data

        action = data.get("action", "get_questions")
        native = self._get_native()

        if native is None:
            return self._python_fallback(data, action)

        try:
            if action == "start":
                return self._start_session(native, data)
            elif action == "get_questions":
                return self._get_questions(native, data)
            elif action == "submit_answer":
                return self._submit_answer(native, data)
            elif action == "submit_answers":
                return self._submit_answers(native, data)
            elif action == "validate":
                return self._validate_answer(native, data)
            elif action == "progress":
                return self._get_progress(native, data)
            elif action == "is_complete":
                return self._is_complete(native, data)
            elif action == "finalize":
                return self._finalize(native, data)
            elif action == "suggestions":
                return self._get_suggestions(native, data)
            else:
                return InteractiveCollectionResult(source="deterministic")
        except Exception:
            return self.fallback(data)

    # ── Rust-backed methods ────────────────────────────────────

    def _start_session(self, native: Any, data: Dict[str, Any]) -> InteractiveCollectionResult:
        session, template_dict = native["completer_start_session"](data.get("niche_id", ""))
        return InteractiveCollectionResult(
            session_id=session.session_id,
            niche_id=session.niche_id,
            completion_pct=0.0,
            is_complete=False,
            round_number=0,
            source="deterministic",
        )

    def _get_questions(self, native: Any, data: Dict[str, Any]) -> InteractiveCollectionResult:
        session = data.get("session")
        template_dict = data.get("template_dict")
        if session is None or template_dict is None:
            return InteractiveCollectionResult(source="deterministic")
        questions = native["completer_get_questions"](session, template_dict)
        question_dicts = [
            {
                "field_name": q.field_name, "display_name": q.display_name,
                "field_type": q.field_type, "section_id": q.section_id,
                "description": q.description, "is_required": q.is_required,
                "order": q.order, "suggestions": q.suggestions,
                "enum_variants": q.enum_variants, "default_value": q.default_value,
                "validation_hint": q.validation_hint,
            }
            for q in questions[:MAX_QUESTIONS_PER_ROUND]
        ]
        progress = native["completer_get_progress"](session, template_dict)
        return InteractiveCollectionResult(
            session_id=session.session_id, niche_id=session.niche_id,
            questions=question_dicts,
            still_missing=progress.get("missing_required", 0),
            completion_pct=progress.get("completion_pct", 0.0),
            is_complete=progress.get("missing_required", 0) == 0,
            round_number=session.round_count, source="deterministic",
        )

    def _submit_answer(self, native: Any, data: Dict[str, Any]) -> InteractiveCollectionResult:
        session = data.get("session")
        template_dict = data.get("template_dict")
        field_name = data.get("field_name", "")
        value = str(data.get("value", ""))[:MAX_ANSWER_LENGTH]
        if session is None or template_dict is None or not field_name:
            return InteractiveCollectionResult(source="deterministic")
        updated_session, applied = native["completer_submit_answer"](session, template_dict, field_name, value)
        progress = native["completer_get_progress"](updated_session, template_dict)
        return InteractiveCollectionResult(
            session_id=updated_session.session_id, niche_id=updated_session.niche_id,
            answers_applied=1 if applied else 0, answers_rejected=0 if applied else 1,
            still_missing=progress.get("missing_required", 0),
            completion_pct=progress.get("completion_pct", 0.0),
            is_complete=progress.get("missing_required", 0) == 0,
            round_number=updated_session.round_count, source="deterministic",
        )

    def _submit_answers(self, native: Any, data: Dict[str, Any]) -> InteractiveCollectionResult:
        session = data.get("session")
        template_dict = data.get("template_dict")
        answers = data.get("answers", {})
        if session is None or template_dict is None or not answers:
            return InteractiveCollectionResult(source="deterministic")
        updated_session, count = native["completer_submit_answers"](session, template_dict, answers)
        progress = native["completer_get_progress"](updated_session, template_dict)
        return InteractiveCollectionResult(
            session_id=updated_session.session_id, niche_id=updated_session.niche_id,
            answers_applied=count, answers_rejected=len(answers) - count,
            still_missing=progress.get("missing_required", 0),
            completion_pct=progress.get("completion_pct", 0.0),
            is_complete=progress.get("missing_required", 0) == 0,
            round_number=updated_session.round_count, source="deterministic",
        )

    def _validate_answer(self, native: Any, data: Dict[str, Any]) -> InteractiveCollectionResult:
        field_type = data.get("field_type", "text")
        value = str(data.get("value", ""))
        is_valid, _ = native["completer_validate_answer"](field_type, value)
        return InteractiveCollectionResult(
            answers_applied=1 if is_valid else 0,
            answers_rejected=0 if is_valid else 1,
            is_complete=False, source="deterministic",
        )

    def _get_progress(self, native: Any, data: Dict[str, Any]) -> InteractiveCollectionResult:
        session = data.get("session")
        template_dict = data.get("template_dict")
        if session is None or template_dict is None:
            return InteractiveCollectionResult(source="deterministic")
        progress = native["completer_get_progress"](session, template_dict)
        return InteractiveCollectionResult(
            session_id=session.session_id, niche_id=session.niche_id,
            still_missing=progress.get("missing_required", 0),
            completion_pct=progress.get("completion_pct", 0.0),
            is_complete=progress.get("missing_required", 0) == 0,
            round_number=session.round_count, source="deterministic",
        )

    def _is_complete(self, native: Any, data: Dict[str, Any]) -> InteractiveCollectionResult:
        session = data.get("session")
        template_dict = data.get("template_dict")
        if session is None or template_dict is None:
            return InteractiveCollectionResult(source="deterministic")
        complete = native["completer_is_complete"](session, template_dict)
        return InteractiveCollectionResult(
            session_id=session.session_id, niche_id=session.niche_id,
            is_complete=complete, round_number=session.round_count,
            source="deterministic",
        )

    def _finalize(self, native: Any, data: Dict[str, Any]) -> InteractiveCollectionResult:
        session = data.get("session")
        template_dict = data.get("template_dict")
        if session is None or template_dict is None:
            return InteractiveCollectionResult(source="deterministic")
        result = native["completer_finalize"](session, template_dict)
        return InteractiveCollectionResult(
            session_id=result.session_id, niche_id=result.niche_id,
            completion_pct=result.completion_pct, is_complete=result.is_complete,
            round_number=result.total_rounds, source="deterministic",
        )

    def _get_suggestions(self, native: Any, data: Dict[str, Any]) -> InteractiveCollectionResult:
        field_name = data.get("field_name", "")
        field_type = data.get("field_type", "text")
        if not field_name:
            return InteractiveCollectionResult(source="deterministic")
        suggestions = native["completer_get_field_suggestions"](field_name, field_type)
        return InteractiveCollectionResult(
            questions=[{"field_name": field_name, "suggestions": suggestions}],
            source="deterministic",
        )

    # ── Python Fallback ────────────────────────────────────────

    def _python_fallback(self, data: Dict[str, Any], action: str) -> InteractiveCollectionResult:
        """Full deterministic Python fallback when Rust extension is not available."""
        if action == "start":
            return self._py_start(data)
        elif action == "get_questions":
            return self._py_get_questions(data)
        elif action == "submit_answer":
            return self._py_submit_answer(data)
        elif action == "submit_answers":
            return self._py_submit_answers(data)
        elif action == "validate":
            return self._py_validate(data)
        elif action == "progress":
            return self._py_progress(data)
        elif action == "is_complete":
            return self._py_is_complete(data)
        elif action == "finalize":
            return self._py_finalize(data)
        elif action == "suggestions":
            return self._py_suggestions(data)
        return InteractiveCollectionResult(source="python_fallback")

    def _py_start(self, data: Dict[str, Any]) -> InteractiveCollectionResult:
        niche_id = data.get("niche_id", "unknown")
        session = _CompletionSession(niche_id)
        self._python_sessions[session.session_id] = session
        return InteractiveCollectionResult(
            session_id=session.session_id, niche_id=niche_id,
            completion_pct=0.0, is_complete=False, round_number=0,
            source="python_fallback",
        )

    def _py_get_questions(self, data: Dict[str, Any]) -> InteractiveCollectionResult:
        template_dict = data.get("template_dict", {})
        session_id = data.get("session_id", "")
        session = self._python_sessions.get(session_id)

        if not template_dict or not session:
            return InteractiveCollectionResult(source="python_fallback")

        questions = self._extract_questions_from_template(template_dict, session)
        progress = self._calculate_progress(template_dict, session)

        session.round_count += 1

        return InteractiveCollectionResult(
            session_id=session_id, niche_id=session.niche_id,
            questions=questions[:MAX_QUESTIONS_PER_ROUND],
            still_missing=progress["missing_required"],
            completion_pct=progress["completion_pct"],
            is_complete=progress["missing_required"] == 0,
            round_number=session.round_count,
            source="python_fallback",
        )

    def _py_submit_answer(self, data: Dict[str, Any]) -> InteractiveCollectionResult:
        session_id = data.get("session_id", "")
        template_dict = data.get("template_dict", {})
        field_name = data.get("field_name", "")
        value = str(data.get("value", ""))[:MAX_ANSWER_LENGTH]
        field_type = data.get("field_type", "text")

        session = self._python_sessions.get(session_id)
        if not session or not template_dict or not field_name:
            return InteractiveCollectionResult(source="python_fallback")

        # Validate
        is_valid = self._validate_field_value(field_type, value, data.get("enum_variants", []))
        applied = 0
        rejected = 0

        if is_valid:
            session.answers[field_name] = value
            self._apply_answer_to_template(template_dict, field_name, value)
            applied = 1
        else:
            rejected = 1

        progress = self._calculate_progress(template_dict, session)

        return InteractiveCollectionResult(
            session_id=session_id, niche_id=session.niche_id,
            answers_applied=applied, answers_rejected=rejected,
            still_missing=progress["missing_required"],
            completion_pct=progress["completion_pct"],
            is_complete=progress["missing_required"] == 0,
            round_number=session.round_count,
            source="python_fallback",
        )

    def _py_submit_answers(self, data: Dict[str, Any]) -> InteractiveCollectionResult:
        session_id = data.get("session_id", "")
        template_dict = data.get("template_dict", {})
        answers = data.get("answers", {})

        session = self._python_sessions.get(session_id)
        if not session or not template_dict or not answers:
            return InteractiveCollectionResult(source="python_fallback")

        applied = 0
        rejected = 0
        for field_name, value in answers.items():
            value_str = str(value)[:MAX_ANSWER_LENGTH]
            if self._validate_field_value("text", value_str, []):
                session.answers[field_name] = value_str
                self._apply_answer_to_template(template_dict, field_name, value_str)
                applied += 1
            else:
                rejected += 1

        progress = self._calculate_progress(template_dict, session)

        return InteractiveCollectionResult(
            session_id=session_id, niche_id=session.niche_id,
            answers_applied=applied, answers_rejected=rejected,
            still_missing=progress["missing_required"],
            completion_pct=progress["completion_pct"],
            is_complete=progress["missing_required"] == 0,
            round_number=session.round_count,
            source="python_fallback",
        )

    def _py_validate(self, data: Dict[str, Any]) -> InteractiveCollectionResult:
        field_type = data.get("field_type", "text")
        value = str(data.get("value", ""))
        is_valid = self._validate_field_value(field_type, value, data.get("enum_variants", []))
        return InteractiveCollectionResult(
            answers_applied=1 if is_valid else 0,
            answers_rejected=0 if is_valid else 1,
            is_complete=False, source="python_fallback",
        )

    def _py_progress(self, data: Dict[str, Any]) -> InteractiveCollectionResult:
        template_dict = data.get("template_dict", {})
        session_id = data.get("session_id", "")
        session = self._python_sessions.get(session_id)
        if not template_dict or not session:
            return InteractiveCollectionResult(source="python_fallback")
        progress = self._calculate_progress(template_dict, session)
        return InteractiveCollectionResult(
            session_id=session_id, niche_id=session.niche_id,
            still_missing=progress["missing_required"],
            completion_pct=progress["completion_pct"],
            is_complete=progress["missing_required"] == 0,
            round_number=session.round_count,
            source="python_fallback",
        )

    def _py_is_complete(self, data: Dict[str, Any]) -> InteractiveCollectionResult:
        template_dict = data.get("template_dict", {})
        session_id = data.get("session_id", "")
        session = self._python_sessions.get(session_id)
        if not template_dict or not session:
            return InteractiveCollectionResult(source="python_fallback")
        progress = self._calculate_progress(template_dict, session)
        return InteractiveCollectionResult(
            session_id=session_id, niche_id=session.niche_id,
            is_complete=progress["missing_required"] == 0,
            round_number=session.round_count,
            source="python_fallback",
        )

    def _py_finalize(self, data: Dict[str, Any]) -> InteractiveCollectionResult:
        template_dict = data.get("template_dict", {})
        session_id = data.get("session_id", "")
        session = self._python_sessions.get(session_id)
        if not template_dict or not session:
            return InteractiveCollectionResult(source="python_fallback")
        progress = self._calculate_progress(template_dict, session)
        return InteractiveCollectionResult(
            session_id=session_id, niche_id=session.niche_id,
            completion_pct=progress["completion_pct"],
            is_complete=progress["missing_required"] == 0,
            round_number=session.round_count,
            source="python_fallback",
        )

    def _py_suggestions(self, data: Dict[str, Any]) -> InteractiveCollectionResult:
        field_name = data.get("field_name", "")
        field_type = data.get("field_type", "text")
        if not field_name:
            return InteractiveCollectionResult(source="python_fallback")
        suggestions = _FIELD_SUGGESTIONS.get(field_name, [])
        if not suggestions and field_type == "boolean":
            suggestions = ["true", "false"]
        elif not suggestions and field_type == "currency":
            suggestions = ["USD", "EUR", "MXN", "COP"]
        return InteractiveCollectionResult(
            questions=[{"field_name": field_name, "suggestions": suggestions}],
            source="python_fallback",
        )

    # ── Python Fallback Helpers ────────────────────────────────

    def _extract_questions_from_template(
        self, template_dict: Dict[str, Any], session: _CompletionSession,
    ) -> List[Dict[str, Any]]:
        """Extract questions for missing required fields from template."""
        questions = []
        template = template_dict.get("template", template_dict)
        sections = template.get("sections", {})

        for section_id, section in sections.items():
            if not isinstance(section, dict):
                continue
            fields = section.get("fields", {})
            for field_name, field_def in fields.items():
                if not isinstance(field_def, dict):
                    continue
                # Skip already answered fields
                if field_name in session.answers:
                    continue
                # Skip non-required fields that have defaults
                is_required = field_def.get("required", False)
                if not is_required and field_def.get("default") is not None:
                    continue
                questions.append({
                    "field_name": field_name,
                    "display_name": field_def.get("display_name", field_name.replace("_", " ").title()),
                    "field_type": field_def.get("type", "text"),
                    "section_id": section_id,
                    "description": field_def.get("description", ""),
                    "is_required": is_required,
                    "order": field_def.get("order", len(questions)),
                    "suggestions": _FIELD_SUGGESTIONS.get(field_name, field_def.get("suggestions", [])),
                    "enum_variants": field_def.get("enum", []),
                    "default_value": field_def.get("default"),
                    "validation_hint": field_def.get("validation_hint", ""),
                })

        # Sort: required first, then by order
        questions.sort(key=lambda q: (not q["is_required"], q["order"]))
        return questions

    def _calculate_progress(
        self, template_dict: Dict[str, Any], session: _CompletionSession,
    ) -> Dict[str, Any]:
        """Calculate completion progress from template and session answers."""
        template = template_dict.get("template", template_dict)
        sections = template.get("sections", {})

        total_fields = 0
        filled_fields = 0
        missing_required = 0

        for section_id, section in sections.items():
            if not isinstance(section, dict):
                continue
            fields = section.get("fields", {})
            for field_name, field_def in fields.items():
                if not isinstance(field_def, dict):
                    continue
                total_fields += 1
                if field_name in session.answers or field_def.get("default") is not None:
                    filled_fields += 1
                elif field_def.get("required", False):
                    missing_required += 1

        completion_pct = (filled_fields / total_fields * 100.0) if total_fields > 0 else 0.0

        return {
            "total_fields": total_fields,
            "filled_fields": filled_fields,
            "missing_required": missing_required,
            "completion_pct": round(completion_pct, 1),
        }

    def _validate_field_value(
        self, field_type: str, value: str, enum_variants: List[str],
    ) -> bool:
        """Validate a field value by type (deterministic)."""
        if not value or len(value) > MAX_ANSWER_LENGTH:
            return False

        # Enum validation
        if enum_variants and field_type == "enum":
            return value in enum_variants

        # Type-specific validation
        validator = _FIELD_VALIDATORS.get(field_type)
        if validator is not None:
            try:
                return validator(value)
            except Exception:
                return False

        # Default: non-empty string
        return len(value.strip()) > 0

    def _apply_answer_to_template(
        self, template_dict: Dict[str, Any], field_name: str, value: str,
    ) -> None:
        """Apply an answer to the template dict in-place."""
        template = template_dict.get("template", template_dict)
        sections = template.get("sections", {})

        for section_id, section in sections.items():
            if not isinstance(section, dict):
                continue
            fields = section.get("fields", {})
            if field_name in fields:
                if isinstance(fields[field_name], dict):
                    fields[field_name]["value"] = value
                else:
                    fields[field_name] = value
                break

    def fallback(self, input_data: Any) -> InteractiveCollectionResult:
        """Safe fallback: empty collection result."""
        return InteractiveCollectionResult(
            is_complete=False,
            source="fallback",
        )
