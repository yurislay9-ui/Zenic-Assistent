"""Core logic for llm_translator."""

from __future__ import annotations
import json
import logging
import re
import time
from typing import Any, Dict, Optional
from ._types import *
from ._mixin_fallback import FallbackMixin

logger = logging.getLogger("zenic_agents.conversational.llm_translator")

class LLMTranslator(FallbackMixin):
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
