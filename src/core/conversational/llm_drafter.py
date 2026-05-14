"""
LLM Drafter — Converts DAG execution results into natural language responses.

Takes the structured output from the DAG engine (code results, error reports,
analysis summaries, etc.) and drafts human-readable responses in the
configured personality and channel format.

Personalities:
  - zenic: Balanced, professional, slightly warm (default)
  - logic: Direct, concise, technical, no fluff
  - nova: Energetic, friendly, emoji-aware, encouraging

Channels:
  - telegram: MarkdownV2 with inline keyboard awareness
  - discord: Embeds + markdown
  - web: HTML-safe plain text
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("zenic_agents.conversational.llm_drafter")

# ─── Personality Prompts ──────────────────────────────────────

PERSONALITY_PROMPTS: Dict[str, str] = {
    "zenic": (
        "You are Zenic, a professional and approachable AI assistant. "
        "You communicate clearly, use structured formatting when helpful, "
        "and add brief context when the user might benefit from it. "
        "Be warm but concise. Avoid excessive emojis."
    ),
    "logic": (
        "You are Logic, a precise and technical AI assistant. "
        "You deliver information directly and efficiently. "
        "No greetings, no fluff, no emojis. Just the facts. "
        "Use code blocks and bullet points for clarity."
    ),
    "nova": (
        "You are Nova, an energetic and friendly AI assistant. "
        "You're encouraging, use a few well-placed emojis, and make "
        "technical topics approachable. Celebrate successes and "
        "frame errors as learning opportunities."
    ),
}

# ─── Channel formatters ───────────────────────────────────────

CHANNEL_FORMATTERS = {
    "telegram", "discord", "web", "cli",
}


class LLMDrafter:
    """Converts DAG execution results into natural language responses.

    Primary path: LLM-based drafting via MiniAIEngine.chat().
    Fallback path: Deterministic template-based response generation.
    """

    def __init__(
        self,
        llm_engine: Optional[Any] = None,
        default_personality: str = "zenic",
        default_channel: str = "cli",
        max_retries: int = 1,
    ) -> None:
        """
        Args:
            llm_engine: MiniAIEngine instance (or any object with .chat()).
                        If None, drafter operates in template-only mode.
            default_personality: Default personality for responses.
            default_channel: Default channel format for responses.
            max_retries: Number of LLM retries on failure.
        """
        self._llm = llm_engine
        self._default_personality = default_personality
        self._default_channel = default_channel
        self._max_retries = max_retries
        self._stats = {
            "total_drafts": 0,
            "llm_drafts": 0,
            "template_drafts": 0,
            "error_drafts": 0,
        }

    # ─── Public API ────────────────────────────────────────────

    def draft(
        self,
        dag_result: Dict,
        conversation_context: Optional[Dict] = None,
        personality: Optional[str] = None,
    ) -> str:
        """Convert DAG output to natural language.

        Args:
            dag_result: Structured result from the DAG engine.
            conversation_context: Optional context with session info, history, etc.
            personality: Personality to use (zenic, logic, nova).

        Returns:
            Natural language response string.
        """
        start = time.time()
        self._stats["total_drafts"] += 1
        personality = personality or self._default_personality
        conversation_context = conversation_context or {}

        # Handle error results
        status = dag_result.get("status", "UNKNOWN")
        if status in ("ERROR", "UNAVAILABLE", "NO_OP"):
            self._stats["error_drafts"] += 1
            return self._draft_error(dag_result, personality)

        # Try LLM path
        drafted = self._try_llm_draft(dag_result, conversation_context, personality)

        if drafted is None:
            # Fallback to templates
            drafted = self._deterministic_draft(dag_result)
            self._stats["template_drafts"] += 1
        else:
            self._stats["llm_drafts"] += 1

        # Apply channel formatting
        channel = conversation_context.get("channel", self._default_channel)
        if channel in CHANNEL_FORMATTERS:
            drafted = self._format_by_channel(drafted, channel)

        elapsed_ms = (time.time() - start) * 1000
        logger.debug(
            f"Drafted response in {elapsed_ms:.1f}ms "
            f"(status={status}, personality={personality})"
        )

        return drafted

    # ─── LLM Path ──────────────────────────────────────────────

    def _try_llm_draft(
        self,
        dag_result: Dict,
        context: Dict,
        personality: str,
    ) -> Optional[str]:
        """Attempt LLM-based drafting with retries."""
        if self._llm is None:
            return None
        if hasattr(self._llm, 'is_loaded') and not self._llm.is_loaded:
            return None

        prompt = self._build_prompt(dag_result, context, personality)

        for attempt in range(self._max_retries + 1):
            try:
                raw = self._call_llm(prompt)
                if raw and len(raw.strip()) > 5:
                    # Strip thinking tokens from Qwen3
                    cleaned = re.sub(r'<think[^>]*>.*?</think\s*>', '', raw, flags=re.DOTALL)
                    return cleaned.strip()
            except Exception as e:
                logger.warning(f"LLM draft attempt {attempt + 1} failed: {e}")

        return None

    def _build_prompt(
        self,
        dag_result: Dict,
        context: Dict,
        personality: str,
    ) -> str:
        """Build the drafting prompt for the LLM."""
        personality_prompt = PERSONALITY_PROMPTS.get(personality, PERSONALITY_PROMPTS["zenic"])

        # Build a concise summary of the DAG result
        status = dag_result.get("status", "UNKNOWN")
        code = dag_result.get("code", "")
        error = dag_result.get("error", "")
        explanations = dag_result.get("explanations", [])
        route = dag_result.get("route", "")
        processing_time = dag_result.get("processing_time_ms", 0)
        verdict = dag_result.get("verdict", "")

        result_summary = f"Status: {status}\n"
        if code:
            # Truncate code to avoid token overflow
            truncated_code = code[:800] + ("..." if len(code) > 800 else "")
            result_summary += f"Code generated:\n```\n{truncated_code}\n```\n"
        if error:
            result_summary += f"Error: {error}\n"
        if explanations:
            result_summary += "Explanations:\n"
            for exp in explanations[:5]:
                result_summary += f"  - {exp}\n"
        if route:
            result_summary += f"Route taken: {route}\n"
        if verdict:
            result_summary += f"Verdict: {verdict}\n"
        if processing_time:
            result_summary += f"Processing time: {processing_time:.0f}ms\n"

        # Include recent conversation context
        recent_history = context.get("recent_history", [])
        history_str = ""
        if recent_history:
            for msg in recent_history[-2:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")[:100]
                history_str += f"  {role}: {content}\n"

        language_hint = ""
        detected_lang = context.get("language", "")
        if detected_lang:
            language_hint = f"Respond in {detected_lang}.\n"

        return (
            f"{personality_prompt}\n\n"
            f"{language_hint}"
            f"The following is the result of a code execution engine. "
            f"Explain it to the user in a clear, helpful way.\n\n"
            f"Conversation context:\n{history_str}\n"
            f"Engine result:\n{result_summary}\n\n"
            f"Your response:"
        )

    # ─── Channel Formatting ────────────────────────────────────

    def _format_by_channel(self, text: str, channel: str) -> str:
        """Format text for a specific channel.

        Args:
            text: The drafted response text.
            channel: Target channel (telegram, discord, web, cli).

        Returns:
            Formatted text appropriate for the channel.
        """
        if channel == "telegram":
            return self._format_telegram(text)
        elif channel == "discord":
            return self._format_discord(text)
        elif channel == "web":
            return self._format_web(text)
        else:
            return text

    @staticmethod
    def _format_telegram(text: str) -> str:
        """Format text for Telegram (MarkdownV2 compatible).

        Telegram MarkdownV2 requires escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
        Code blocks are preserved without internal escaping.
        """
        # Preserve code blocks using alphanumeric-only placeholders
        code_blocks: list[str] = []
        def _save_code(match: re.Match) -> str:
            code_blocks.append(match.group(0))
            return f"ZENICDRCODE{len(code_blocks) - 1}ENDZENIC"

        text = re.sub(r'```[\s\S]*?```', _save_code, text)

        # Preserve inline code
        inline_codes: list[str] = []
        def _save_inline(match: re.Match) -> str:
            inline_codes.append(match.group(0))
            return f"ZENICDRINLINE{len(inline_codes) - 1}ENDZENIC"

        text = re.sub(r'`[^`]+`', _save_inline, text)

        # Escape special characters for MarkdownV2
        special_chars = r'_*[]()~>#+-=|{}.!'
        for char in special_chars:
            text = text.replace(char, f'\\{char}')

        # Restore inline code
        for i, code in enumerate(inline_codes):
            text = text.replace(f"ZENICDRINLINE{i}ENDZENIC", code)

        # Restore code blocks (unescaped inside code blocks)
        for i, block in enumerate(code_blocks):
            text = text.replace(f"ZENICDRCODE{i}ENDZENIC", block)

        return text

    @staticmethod
    def _format_discord(text: str) -> str:
        """Format text for Discord (markdown compatible)."""
        # Discord supports standard markdown, so minimal changes needed.
        # Just ensure we don't exceed 2000 chars per message (handle in adapter).
        return text

    @staticmethod
    def _format_web(text: str) -> str:
        """Format text for web (HTML-safe)."""
        # Escape HTML special characters
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        return text

    # ─── Template-based Fallback ───────────────────────────────

    def _deterministic_draft(self, dag_result: Dict) -> str:
        """When LLM unavailable, uses template-based response generation."""
        status = dag_result.get("status", "UNKNOWN")
        code = dag_result.get("code", "")
        error = dag_result.get("error", "")
        explanations = dag_result.get("explanations", [])
        route = dag_result.get("route", "")
        processing_time = dag_result.get("processing_time_ms", 0)
        verdict = dag_result.get("verdict", "")
        cache_source = dag_result.get("cache_source", "")

        parts: list[str] = []

        if status == "SUCCESS":
            if code:
                parts.append("Here's the generated code:")
                # Truncate for readability
                display_code = code[:1500] + ("\n..." if len(code) > 1500 else "")
                parts.append(f"```\n{display_code}\n```")
            else:
                parts.append("Operation completed successfully.")

            if verdict:
                parts.append(f"**Verdict:** {verdict}")

            if cache_source:
                parts.append(f"*(Result from cache: {cache_source})*")

        elif status == "CACHED":
            parts.append("Retrieved cached result:")
            if code:
                display_code = code[:1500] + ("\n..." if len(code) > 1500 else "")
                parts.append(f"```\n{display_code}\n```")

        elif status == "REJECTED":
            parts.append("The request was rejected for safety reasons.")
            if verdict:
                parts.append(f"**Reason:** {verdict}")

        else:
            parts.append(f"Operation status: {status}")

        if explanations:
            parts.append("\n**Details:**")
            for exp in explanations[:5]:
                parts.append(f"  • {exp}")

        if route:
            parts.append(f"  *Route: {route}*")

        if processing_time > 0:
            parts.append(f"  *Completed in {processing_time:.0f}ms*")

        return "\n".join(parts) if parts else "Operation processed."

    def _draft_error(self, dag_result: Dict, personality: str) -> str:
        """Draft a user-friendly error message."""
        status = dag_result.get("status", "ERROR")
        error = dag_result.get("error", "An unknown error occurred")

        if personality == "nova":
            return (
                f"Oops! Something went wrong 😅\n\n"
                f"**Error:** {error}\n\n"
                f"Don't worry — let's try again! You can rephrase your request "
                f"or try a simpler version of what you need."
            )
        elif personality == "logic":
            return (
                f"ERROR [{status}]\n\n"
                f"Detail: {error}\n\n"
                f"Suggested actions:\n"
                f"  1. Verify input parameters\n"
                f"  2. Check system status\n"
                f"  3. Retry with simplified request"
            )
        else:  # zenic
            return (
                f"I encountered an issue while processing your request.\n\n"
                f"**Error:** {error}\n\n"
                f"You can try rephrasing your request, or I can help you "
                f"troubleshoot the issue. What would you prefer?"
            )

    # ─── LLM Helper ────────────────────────────────────────────

    def _call_llm(self, prompt: str) -> Optional[str]:
        """Call the LLM engine safely."""
        try:
            if hasattr(self._llm, 'chat'):
                return self._llm.chat(prompt, max_tokens=1024)
            elif hasattr(self._llm, '_call_llm'):
                return self._llm._call_llm(
                    system_prompt="You are drafting a response to a user. Be concise and helpful.",
                    user_prompt=prompt,
                    max_tokens=1024,
                )
        except Exception as e:
            logger.warning(f"LLM draft call failed: {e}")
        return None

    # ─── Properties ────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """Drafting statistics."""
        return {**self._stats}

    @property
    def llm_available(self) -> bool:
        """Whether the LLM engine is available for drafting."""
        if self._llm is None:
            return False
        if hasattr(self._llm, 'is_loaded'):
            return self._llm.is_loaded
        return True
