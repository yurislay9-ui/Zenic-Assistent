"""interactive_data_collector — Core implementation."""

from __future__ import annotations

from ._types import *  # noqa: F403
from ._helpers import _py_start, _py_get_questions, _py_submit_answer, _py_submit_answers, _py_validate, _py_progress, _py_is_complete, _py_finalize, _py_suggestions, _extract_questions_from_template, _calculate_progress, _validate_field_value, _apply_answer_to_template

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

    def fallback(self, input_data: Any) -> InteractiveCollectionResult:
        """Safe fallback: empty collection result."""
        return InteractiveCollectionResult(
            is_complete=False,
            source="fallback",
        )
