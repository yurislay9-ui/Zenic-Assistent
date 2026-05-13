"""
LLM Translator — Converts natural language input into structured DAG requests.

Bridges the gap between free-form user text and the structured request format
that the DAG orchestrator expects. Uses the local LLM (MiniAIEngine) when
available, with deterministic keyword-based fallback.

Output schema:
  {
      "intent": str,          # e.g. "code_create", "question", "command"
      "entities": dict,       # extracted entities (files, langs, frameworks...)
      "action_type": str,     # e.g. "CREATE", "DEBUG", "SEARCH"
      "config": dict,         # parameters for the DAG action
      "confidence": float,    # 0.0-1.0
  }
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("zenic_agents.conversational.llm_translator")

# ─── Valid schemas for validation ──────────────────────────────

VALID_INTENTS = frozenset({
    "chat", "question", "command", "feedback", "config",
    "code_create", "code_refactor", "code_debug", "code_optimize",
    "code_analyze", "code_explain", "business", "automation",
    "unknown",
})

VALID_ACTION_TYPES = frozenset({
    "CREATE", "REFACTOR", "DELETE", "SEARCH",
    "ANALYZE", "EXPLAIN", "DEBUG", "OPTIMIZE",
    "CHAT", "COMMAND", "CONFIG", "QUESTION",
})

INTENT_TO_ACTION = {
    "code_create": "CREATE",
    "code_refactor": "REFACTOR",
    "code_debug": "DEBUG",
    "code_optimize": "OPTIMIZE",
    "code_analyze": "ANALYZE",
    "code_explain": "EXPLAIN",
    "question": "SEARCH",
    "automation": "CREATE",
    "business": "ANALYZE",
    "command": "COMMAND",
    "config": "CONFIG",
    "chat": "CHAT",
    "feedback": "CHAT",
}


class LLMTranslator:
    """Converts natural language input into structured DAG requests.

    Primary path: LLM-based translation via MiniAIEngine.chat().
    Fallback path: Deterministic keyword matching + IntentClassifier.
    """

    def __init__(
        self,
        llm_engine: Optional[Any] = None,
        max_retries: int = 2,
        retry_delay_s: float = 0.5,
    ) -> None:
        """
        Args:
            llm_engine: MiniAIEngine instance (or any object with a .chat() method).
                        If None, translator operates in deterministic-only mode.
            max_retries: Number of LLM retries on parse failure.
            retry_delay_s: Delay between retries in seconds.
        """
        self._llm = llm_engine
        self._max_retries = max_retries
        self._retry_delay_s = retry_delay_s
        self._stats = {
            "total_translations": 0,
            "llm_translations": 0,
            "fallback_translations": 0,
            "parse_failures": 0,
        }

    # ─── Public API ────────────────────────────────────────────

    def translate(self, user_input: str, context: Optional[Dict] = None) -> Dict:
        """Convert NL input to a structured DAG request.

        Args:
            user_input: Raw user text.
            context: Optional context dict (session_id, history, etc.).

        Returns:
            Structured request dict with intent, entities, action_type,
            config, and confidence. Returns empty dict with low confidence
            when uncertain.
        """
        start = time.time()
        self._stats["total_translations"] += 1
        context = context or {}

        if not user_input or not user_input.strip():
            return self._low_confidence_result("empty_input")

        # Try LLM path first
        result = self._try_llm_translate(user_input, context)

        if result is None:
            # Fallback to deterministic
            result = self._deterministic_fallback(user_input)
            self._stats["fallback_translations"] += 1
        else:
            self._stats["llm_translations"] += 1

        # Validate and sanitize
        result = self._validate_result(result)

        elapsed_ms = (time.time() - start) * 1000
        result["translation_time_ms"] = round(elapsed_ms, 2)
        result["translation_source"] = result.get("translation_source", "unknown")

        logger.debug(
            f"Translated '{user_input[:50]}' -> intent={result.get('intent')}, "
            f"action={result.get('action_type')}, conf={result.get('confidence', 0):.2f}"
        )
        return result

    # ─── LLM Path ──────────────────────────────────────────────

    def _try_llm_translate(self, user_input: str, context: Dict) -> Optional[Dict]:
        """Attempt LLM-based translation with retries."""
        if self._llm is None:
            return None

        # Check if LLM is available
        if hasattr(self._llm, 'is_loaded') and not self._llm.is_loaded:
            return None

        prompt = self._build_prompt(user_input, context)

        for attempt in range(self._max_retries + 1):
            try:
                raw_output = self._call_llm(prompt)
                if raw_output is None:
                    continue

                parsed = self._parse_response(raw_output)
                if parsed and parsed.get("intent"):
                    parsed["translation_source"] = "llm"
                    return parsed

                self._stats["parse_failures"] += 1

            except Exception as e:
                logger.warning(f"LLM translation attempt {attempt + 1} failed: {e}")

            if attempt < self._max_retries:
                time.sleep(self._retry_delay_s * (attempt + 1))

        return None

    def _build_prompt(self, user_input: str, context: Dict) -> str:
        """Build the translation prompt for the LLM."""
        recent_history = context.get("recent_history", [])
        history_str = ""
        if recent_history:
            # Include last 3 turns max
            for msg in recent_history[-3:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")[:100]
                history_str += f"  {role}: {content}\n"

        language_hint = ""
        detected_lang = context.get("language", "")
        if detected_lang:
            language_hint = f"User language: {detected_lang}\n"

        return (
            "You are a request parser. Convert the user message into a structured JSON request.\n"
            "Output ONLY valid JSON with these fields:\n"
            '  "intent": one of [chat, question, command, config, feedback, '
            'code_create, code_refactor, code_debug, code_optimize, code_analyze, '
            'code_explain, business, automation]\n'
            '  "entities": {"files": [], "languages": [], "frameworks": [], '
            '"functions": [], "domains": []}\n'
            '  "action_type": one of [CREATE, REFACTOR, DELETE, SEARCH, ANALYZE, '
            'EXPLAIN, DEBUG, OPTIMIZE, CHAT, COMMAND, CONFIG, QUESTION]\n'
            '  "config": {"target_file": "", "language": "", "scope": "", '
            '"operation_detail": ""}\n'
            '  "confidence": float between 0.0 and 1.0\n\n'
            f"{language_hint}"
            f"Conversation history:\n{history_str}\n"
            f'User message: "{user_input}"\n\n'
            "JSON:"
        )

    def _parse_response(self, llm_output: str) -> Optional[Dict]:
        """Parse LLM output into structured format.

        Tries to extract JSON from the response. If parsing fails,
        attempts to extract structured data from freeform text.
        """
        # Strip thinking tokens from Qwen3
        cleaned = re.sub(r'<think[^>]*>.*?</think\s*>', '', llm_output, flags=re.DOTALL)
        cleaned = cleaned.strip()

        # Try to find JSON in the response
        json_str = self._extract_json(cleaned)
        if json_str:
            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        # Try to extract key-value pairs from freeform text
        return self._extract_structured(cleaned)

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        """Extract JSON block from text."""
        # Try code-block wrapped JSON first
        cb_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
        if cb_match:
            return cb_match.group(1)

        # Try raw JSON
        brace_start = text.find('{')
        brace_end = text.rfind('}')
        if brace_start != -1 and brace_end > brace_start:
            return text[brace_start:brace_end + 1]

        return None

    @staticmethod
    def _extract_structured(text: str) -> Optional[Dict]:
        """Attempt to extract structured data from freeform LLM text."""
        result: Dict[str, Any] = {}

        # Look for intent mentions
        for intent in VALID_INTENTS:
            if intent in text.lower():
                result["intent"] = intent
                break

        # Look for action type mentions
        for action in VALID_ACTION_TYPES:
            if action in text.upper():
                result["action_type"] = action
                break

        # Look for confidence
        conf_match = re.search(r'confidence["\s:]*(0?\.\d+|1\.0|1|0)', text, re.I)
        if conf_match:
            try:
                result["confidence"] = float(conf_match.group(1))
            except ValueError:
                pass

        return result if result else None

    # ─── Deterministic Fallback ────────────────────────────────

    def _deterministic_fallback(self, user_input: str) -> Dict:
        """When LLM unavailable, uses keyword matching + IntentClassifier."""
        try:
            from ..agents_v2.understanding import IntentClassifier, EntityExtractor

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
            # agents_v2 not available — pure keyword matching
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

    # ─── Validation ────────────────────────────────────────────

    def _validate_result(self, result: Dict) -> Dict:
        """Validate and sanitize the translation result against known schemas."""
        if not isinstance(result, dict):
            return self._low_confidence_result("invalid_result_type")

        # Validate intent
        intent = result.get("intent", "unknown")
        if intent not in VALID_INTENTS:
            logger.warning(f"Unknown intent '{intent}', defaulting to 'unknown'")
            result["intent"] = "unknown"

        # Validate action_type
        action_type = result.get("action_type", "")
        if action_type not in VALID_ACTION_TYPES:
            # Try to derive from intent
            result["action_type"] = INTENT_TO_ACTION.get(intent, "SEARCH")

        # Validate confidence
        confidence = result.get("confidence", 0.0)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0
        result["confidence"] = max(0.0, min(1.0, confidence))

        # Ensure entities is a dict
        if not isinstance(result.get("entities"), dict):
            result["entities"] = {}

        # Ensure config is a dict
        if not isinstance(result.get("config"), dict):
            result["config"] = {}

        return result

    @staticmethod
    def _low_confidence_result(reason: str) -> Dict:
        """Return an empty result with low confidence."""
        return {
            "intent": "unknown",
            "entities": {},
            "action_type": "SEARCH",
            "config": {},
            "confidence": 0.1,
            "translation_source": f"low_confidence:{reason}",
        }

    # ─── LLM Helper ────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call the LLM engine safely."""
        try:
            if hasattr(self._llm, 'chat'):
                return self._llm.chat(prompt, max_tokens=512)
            elif hasattr(self._llm, '_call_llm'):
                return self._llm._call_llm(
                    system_prompt="You are a JSON request parser. Output ONLY valid JSON.",
                    user_prompt=prompt,
                    max_tokens=512,
                )
        except Exception as e:
            logger.warning(f"LLM call failed: {e}")
        return None

    # ─── Properties ────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """Translation statistics."""
        return {**self._stats}

    @property
    def llm_available(self) -> bool:
        """Whether the LLM engine is available for translations."""
        if self._llm is None:
            return False
        if hasattr(self._llm, 'is_loaded'):
            return self._llm.is_loaded
        return True  # Assume available if no is_loaded check
