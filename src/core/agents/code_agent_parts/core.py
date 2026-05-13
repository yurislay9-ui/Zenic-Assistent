"""
CodeAgent Core — main class definition with __init__, build_prompt, parse,
run methods and the high-level *_with_runner API.

Extracted from the monolithic code_agent.py (1,043 lines) as part of the
mixin-based modularisation.  This module assembles the final CodeAgent class
from the individual mixins.
"""

import time
import logging
from typing import Any, Dict, Optional, Tuple

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import CodeInput, CodeOutput
from src.core.agents.prompts import AgentPrompts, PromptBuilder
from src.core.agents.code_agent_parts.helpers import (
    CodeAgentHelpersMixin,
    TASK_PROMPTS,
)
from src.core.agents.code_agent_parts.scaffolds import CodeAgentScaffoldsMixin
from src.core.agents.code_agent_parts.fallbacks import CodeAgentFallbacksMixin
from src.core.agents.code_agent_parts.defensive import CodeAgentDefensiveMixin

logger = logging.getLogger(__name__)


class CodeAgent(
    CodeAgentScaffoldsMixin,
    CodeAgentFallbacksMixin,
    CodeAgentDefensiveMixin,
    CodeAgentHelpersMixin,
    BaseAgent[CodeOutput],
):
    """
    Agente de generación y transformación de código que unifica
    CodeGenerator + CodeTransformer + AppGenerator.

    Flujo de ejecución:
    1. build_prompt() → Construye prompt según tipo de tarea
    2. AgentRunner.run() → Intenta LLM → parse_response()
    3. Si LLM falla → fallback determinista por tarea + lenguaje

    El agente unifica la lógica que antes estaba en:
    - CodeGenerator.generate_pipeline_driven_code() (820 líneas)
    - CodeTransformer.refactor_python/fix_python/optimize_function (443 líneas)
    - AppGenerator legacy f-string generation
    """

    def __init__(self, semantic_engine=None, smart_memory=None,
                 template_engine=None) -> None:
        super().__init__(name="code")
        self._semantic_engine = semantic_engine
        self._smart_memory = smart_memory
        self._template_engine = template_engine
        # F4: Criticality adjustments (injected by CriticalityAgent)
        self._criticality_adjustments: Dict[str, Any] = {}

    def wire(self, semantic_engine=None, smart_memory=None,
             template_engine=None) -> None:
        """Cablea dependencias (para inyección post-creación)."""
        if semantic_engine is not None:
            self._semantic_engine = semantic_engine
        if smart_memory is not None:
            self._smart_memory = smart_memory
        if template_engine is not None:
            self._template_engine = template_engine

    def set_criticality_adjustments(self, adjustments: Dict[str, Any]) -> None:
        """F4: Inyecta ajustes de criticalidad desde CriticalityAgent."""
        self._criticality_adjustments = adjustments.get("code_agent", {})

    # ============================================================
    #  BaseAgent INTERFACE
    # ============================================================

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """Construye system + user prompt según tipo de tarea.

        R2 FIX: For 'generate' task, use simplified markdown code block prompt
        instead of JSON prompt. Qwen3-0.6B can produce code blocks much more
        reliably than JSON-wrapped code.
        """
        if isinstance(input_data, CodeInput):
            task = input_data.task
            requirements = input_data.requirements
            language = input_data.language
            existing_code = input_data.existing_code
            constraints = input_data.constraints
        else:
            task = "generate"
            requirements = str(input_data)
            language = "python"
            existing_code = ""
            constraints = {}

        # Use simplified prompt for generate task (0.6B-friendly)
        if task == "generate":
            system_prompt = AgentPrompts.CODE_SYSTEM_GENERATE.replace("{language}", language)
        else:
            system_prompt = TASK_PROMPTS.get(task, AgentPrompts.CODE_SYSTEM_GENERATE_JSON)

        user_prompt = AgentPrompts.CODE_USER.format(
            task=task,
            requirements=requirements[:800],  # R2: increased from 500 to 800
            language=language,
            existing_code=existing_code[:600] if existing_code else "none",  # R2: increased from 300 to 600
        )

        # Add constraints context
        if constraints:
            user_prompt = PromptBuilder.add_context_to_prompt(
                user_prompt, {"constraints": constraints}
            )

        return system_prompt, user_prompt

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[CodeOutput]:
        """Parsea la respuesta del LLM a un CodeOutput válido.

        R2 FIX: Prioritize markdown code block extraction over JSON.
        Qwen3-0.6B can produce code blocks much more reliably than
        JSON-wrapped code. JSON parsing is still attempted as fallback.
        """
        cleaned = self.clean_llm_text(raw_response)

        # Try to extract code from markdown code blocks FIRST
        # (0.6B models produce code blocks more reliably than JSON)
        code_block_result = self._parse_code_blocks(cleaned, source="llm")
        if code_block_result and code_block_result.code:
            return code_block_result

        # Try JSON extraction as fallback
        json_data = self.extract_json(cleaned)
        if json_data and isinstance(json_data, dict):
            return self._json_to_code_output(json_data, source="llm")

        # Last resort: return raw text as code
        if cleaned.strip():
            return CodeOutput(
                code=cleaned.strip(),
                language="python",
                source="llm_raw",
            )
        return None

    def fallback(self, input_data: Any) -> CodeOutput:
        """
        Fallback determinista: generación de código por tarea + lenguaje.

        Sin LLM, sin templates. Generación directa basada en reglas.
        F4: Aplica ajustes de criticalidad si están disponibles.
        """
        start = time.time()

        if isinstance(input_data, CodeInput):
            task = input_data.task
            requirements = input_data.requirements
            language = input_data.language
            existing_code = input_data.existing_code
            constraints = input_data.constraints
        else:
            task = "generate"
            requirements = str(input_data)
            language = "python"
            existing_code = ""
            constraints = {}

        # Route to task-specific fallback
        if task == "transform":
            result = self._fallback_transform(existing_code, requirements, language)
        elif task == "optimize":
            result = self._fallback_optimize(existing_code, language)
        elif task == "fix":
            result = self._fallback_fix(existing_code, language)
        elif task == "scaffold":
            result = self._fallback_scaffold(requirements, language)
        else:
            result = self._fallback_generate(requirements, language, constraints)

        # F4: Apply criticality adjustments to generated code
        result = self._apply_criticality_adjustments(result)

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        result.source = "fallback"
        return result

    # ============================================================
    #  HIGH-LEVEL API
    # ============================================================

    def generate_with_runner(self, runner: Any, requirements: str,
                             language: str = "python",
                             constraints: Optional[Dict[str, Any]] = None) -> CodeOutput:
        """Genera código usando AgentRunner (LLM → fallback)."""
        input_data = CodeInput(
            task="generate", requirements=requirements,
            language=language, constraints=constraints or {},
        )
        result: AgentResult = runner.run(self, input_data)
        if result.success and isinstance(result.data, CodeOutput):
            return result.data
        return self.fallback(input_data)

    def transform_with_runner(self, runner: Any, existing_code: str,
                               requirements: str,
                               language: str = "python") -> CodeOutput:
        """Transforma código usando AgentRunner (LLM → fallback)."""
        input_data = CodeInput(
            task="transform", requirements=requirements,
            language=language, existing_code=existing_code,
        )
        result: AgentResult = runner.run(self, input_data)
        if result.success and isinstance(result.data, CodeOutput):
            return result.data
        return self.fallback(input_data)

    def fix_with_runner(self, runner: Any, existing_code: str,
                         language: str = "python") -> CodeOutput:
        """Corrige código usando AgentRunner (LLM → fallback)."""
        input_data = CodeInput(
            task="fix", requirements="Fix bugs and errors",
            language=language, existing_code=existing_code,
        )
        result: AgentResult = runner.run(self, input_data)
        if result.success and isinstance(result.data, CodeOutput):
            return result.data
        return self.fallback(input_data)
