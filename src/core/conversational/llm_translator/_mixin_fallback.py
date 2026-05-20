"""Fallback translation mixin for LLMTranslator."""

from __future__ import annotations
import logging
from typing import Any, Dict, Optional
from ._types import *

logger = logging.getLogger("zenic_agents.conversational.llm_translator")


class FallbackMixin:
    """Mixin providing deterministic and keyword-based fallback translation methods."""

    def _deterministic_fallback(self, user_input: str) -> Dict:
        """When LLM unavailable, uses keyword matching + IntentClassifier."""
        try:
            from ..agents.understanding import IntentClassifier, EntityExtractor

            classifier = IntentClassifier()
            extractor = EntityExtractor()

            intent_result = classifier.execute(user_input)
            entity_result = extractor.execute(user_input)

            # Map operation to conversational intent
            op_to_intent = {
                "CREATE": "code_create",
                "REFACTOR": "code_refactor",
                "DELETE": "code_create",
                "SEARCH": "question",
                "ANALYZE": "code_analyze",
                "EXPLAIN": "code_explain",
                "DEBUG": "code_debug",
                "OPTIMIZE": "code_optimize",
            }

            intent_str = op_to_intent.get(intent_result.operation, "chat")

            # Check for conversational patterns first
            lower = user_input.lower()
            if lower.startswith(("/",)):
                intent_str = "command"
            elif any(w in lower for w in ("hola", "hey", "hi", "hello", "gracias", "thanks")):
                intent_str = "chat"
            elif any(w in lower for w in ("que es", "what is", "como", "how does", "?")):
                intent_str = "question"
            elif any(w in lower for w in ("configura", "ajusta", "configure", "adjust")):
                intent_str = "config"

            action_type = INTENT_TO_ACTION.get(intent_str, intent_result.operation)
            confidence = min(intent_result.confidence + 0.1, 1.0)  # Slight boost

            return {
                "intent": intent_str,
                "entities": {
                    "files": entity_result.files,
                    "languages": entity_result.langs,
                    "frameworks": entity_result.frameworks,
                    "functions": entity_result.functions,
                    "domains": entity_result.domains,
                },
                "action_type": action_type,
                "config": {
                    "target_file": "",
                    "language": entity_result.langs[0] if entity_result.langs else "",
                    "scope": "",
                    "operation_detail": user_input,
                },
                "confidence": confidence,
                "translation_source": "deterministic",
            }

        except ImportError:
            # agents not available — pure keyword matching
            return self._pure_keyword_fallback(user_input)

    def _pure_keyword_fallback(self, user_input: str) -> Dict:
        """Minimal keyword-only fallback when IntentClassifier is unavailable."""
        lower = user_input.lower()

        intent = "chat"
        action_type = "CHAT"
        confidence = 0.3

        # Simple keyword rules
        code_words = ("crear", "create", "generar", "build", "funcion", "function",
                      "clase", "class", "modulo", "module")
        debug_words = ("debug", "fix", "corregir", "error", "bug", "arreglar")
        question_words = ("que es", "what is", "como", "how", "por que", "why", "?")
        refactor_words = ("refactor", "reestructurar", "limpiar codigo", "clean code")
        analyze_words = ("analizar", "analyze", "revisar", "review", "auditar")
        optimize_words = ("optimizar", "optimize", "mejorar rendimiento", "speed up")
        config_words = ("configura", "ajusta", "configure", "ajustar")
        command_words = ("/start", "/help", "/status", "/cancel")

        if any(w in lower for w in command_words):
            intent, action_type, confidence = "command", "COMMAND", 0.9
        elif any(w in lower for w in config_words):
            intent, action_type, confidence = "config", "CONFIG", 0.7
        elif any(w in lower for w in code_words):
            intent, action_type, confidence = "code_create", "CREATE", 0.6
        elif any(w in lower for w in debug_words):
            intent, action_type, confidence = "code_debug", "DEBUG", 0.6
        elif any(w in lower for w in refactor_words):
            intent, action_type, confidence = "code_refactor", "REFACTOR", 0.6
        elif any(w in lower for w in analyze_words):
            intent, action_type, confidence = "code_analyze", "ANALYZE", 0.6
        elif any(w in lower for w in optimize_words):
            intent, action_type, confidence = "code_optimize", "OPTIMIZE", 0.6
        elif any(w in lower for w in question_words):
            intent, action_type, confidence = "question", "SEARCH", 0.5

        return {
            "intent": intent,
            "entities": {"files": [], "languages": [], "frameworks": [], "functions": [], "domains": []},
            "action_type": action_type,
            "config": {
                "target_file": "",
                "language": "",
                "scope": "",
                "operation_detail": user_input,
            },
            "confidence": confidence,
            "translation_source": "keyword_fallback",
        }
