"""SmartPromptChain - Execution, Validation & Repair Mixin."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ._types import GenerationStep, ChainResult, MAX_LINES_PER_STEP, MAX_REPAIR_ATTEMPTS

logger = logging.getLogger("zenic_agents.code_gen_parts.smart_chain")


class SmartChainExecutionMixin:
    """Mixin providing execution, validation, and repair methods."""

    # ================================================================
    #  EXECUTION
    # ================================================================

    def _execute_step(self, step: GenerationStep, language: str) -> Optional[str]:
        """Execute a single generation step using the LLM."""
        step.attempts += 1

        # Build the full prompt with context
        full_prompt = self._build_prompt(step, language)

        # Try LLM generation
        if self._llm:
            try:
                if hasattr(self._llm, 'generate'):
                    result = self._llm.generate(full_prompt)
                elif callable(self._llm):
                    result = self._llm(full_prompt)
                else:
                    result = None

                if result and isinstance(result, str):
                    # Extract code from markdown blocks if present
                    code = self._extract_code(result, language)
                    if code:
                        return code
                    return result.strip()
            except Exception as e:
                logger.warning(f"SmartPromptChain: LLM generation failed: {e}")

        # M2 ENHANCED: Template-based generation with REAL code (no LLM needed)
        return self._template_fallback(step, language)

    def _build_prompt(self, step: GenerationStep, language: str) -> str:
        """Build a step prompt with context from previous steps."""
        parts = [
            f"TASK: {step.description}",
            f"LANGUAGE: {language}",
            f"MAX LINES: {MAX_LINES_PER_STEP}",
            "",
        ]

        if step.context:
            # Include only the last N lines of context (keep prompt small)
            context_lines = step.context.strip().split('\n')
            if len(context_lines) > 20:
                context_preview = '\n'.join(context_lines[-20:])
                parts.append(f"PREVIOUS CODE (last 20 lines):\n```{language}\n{context_preview}\n```")
            else:
                parts.append(f"PREVIOUS CODE:\n```{language}\n{step.context}\n```")
            parts.append("")

        parts.append(f"GENERATE NOW:\n{step.prompt}")
        parts.append("")
        parts.append("Output ONLY the requested code. No explanations. No markdown fences.")

        return '\n'.join(parts)

    # ================================================================
    #  VALIDATION & REPAIR
    # ================================================================

    def _validate_fragment(self, code: str, language: str) -> bool:
        """Validate a generated code fragment."""
        if not code or len(code.strip()) < 5:
            return False

        if language == "python":
            try:
                compile(code, '<fragment>', 'exec')
                return True
            except SyntaxError as e:
                logger.debug(f"SmartPromptChain: Syntax error in fragment: {e}")
                return False

        # For non-Python, just check it's not empty
        return len(code.strip()) > 10

    def _auto_repair(self, step: GenerationStep, broken_code: str,
                     language: str) -> Tuple[Optional[str], int]:
        """Try to repair a broken code fragment.

        Returns (repaired_code, repair_attempts) or (None, attempts)
        """
        for attempt in range(MAX_REPAIR_ATTEMPTS):
            step.attempts += 1

            # Build repair prompt
            repair_prompt = (
                f"The following {language} code has a syntax error. Fix it.\n\n"
                f"BROKEN CODE:\n```{language}\n{broken_code}\n```\n\n"
                f"TASK: {step.description}\n"
                f"Fix the error and output ONLY the corrected code."
            )

            if self._llm:
                try:
                    if hasattr(self._llm, 'generate'):
                        repaired = self._llm.generate(repair_prompt)
                    elif callable(self._llm):
                        repaired = self._llm(repair_prompt)
                    else:
                        continue

                    if repaired:
                        code = self._extract_code(repaired, language) or repaired.strip()
                        if self._validate_fragment(code, language):
                            return code, attempt + 1
                        broken_code = code  # Try to fix the fix
                except Exception as e:
                    logger.debug(f"SmartPromptChain: Repair attempt {attempt+1} failed: {e}")

        return None, MAX_REPAIR_ATTEMPTS


    def _template_fallback(self, step: GenerationStep, language: str) -> str:
        """Generate code without LLM using predefined templates.

        M2 ENHANCED: These fallbacks now produce REAL functional code
        instead of minimal stubs. Each step type generates substantial,
        working Python code that connects to real executors.
        """
        st = step.step_type
        desc = step.description

        if st == "imports":
            return self._fallback_imports(desc)

        elif st == "schema":
            return self._fallback_schema(desc)

        elif st == "class_def":
            return self._fallback_class_def(desc)

        elif st == "method":
            return self._fallback_method(desc)

        elif st == "tests":
            return self._fallback_tests(desc)

        return f"# Generated step: {step.step_type} — {step.description}\n"
