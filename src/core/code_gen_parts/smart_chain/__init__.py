"""
SmartPromptChain - Fragmented generation for small LLMs (Qwen3-0.6B).

Breaks generation into atomic steps of 20-50 lines each, with context
carry-forward between steps. Each step is manageable for the model.
"""

import logging
from typing import Any, Dict, List, Optional

from ._types import GenerationStep, ChainResult, MAX_LINES_PER_STEP, MAX_REPAIR_ATTEMPTS
from ._planners_mixin import SmartChainPlannersMixin
from ._execution_mixin import SmartChainExecutionMixin
from ._templates_mixin import SmartChainTemplatesMixin
from ._utils_mixin import SmartChainUtilsMixin

logger = logging.getLogger("zenic_agents.code_gen_parts.smart_chain")

__all__ = ["SmartPromptChain", "GenerationStep", "ChainResult"]


class SmartPromptChain(
    SmartChainPlannersMixin,
    SmartChainExecutionMixin,
    SmartChainTemplatesMixin,
    SmartChainUtilsMixin,
):
    """Fragmented code generation for small LLMs."""

    def __init__(self, llm_engine=None, sandbox=None):
        """
        Args:
            llm_engine: MiniAIEngine or any callable that takes (prompt) -> str
            sandbox: Optional ExecutionBridge for validation
        """
        self._llm = llm_engine
        self._sandbox = sandbox

    def generate_code(self, task_description: str, language: str = "python",
                      entity_info: Optional[Dict] = None,
                      max_lines: int = 200) -> ChainResult:
        """Generate code using step-by-step fragmented approach."""
        steps = self.plan_steps(task_description, language, entity_info, max_lines)
        return self.execute_chain(steps, language)

    def plan_steps(self, task_description: str, language: str = "python",
                   entity_info: Optional[Dict] = None,
                   max_lines: int = 200) -> List[GenerationStep]:
        """Decompose a generation task into atomic steps."""
        entity_name = (entity_info or {}).get("name", "Module")
        fields = (entity_info or {}).get("fields", [])
        task_type = self._detect_task_type(task_description)

        if task_type == "crud":
            return self._plan_crud_steps(entity_name, fields, language)
        elif task_type == "auth":
            return self._plan_auth_steps(entity_name, language)
        elif task_type == "integration":
            return self._plan_integration_steps(entity_name, task_description, language)
        elif task_type == "analytics":
            return self._plan_analytics_steps(entity_name, fields, language)
        else:
            return self._plan_generic_steps(entity_name, task_description, language)

    def execute_chain(self, steps: List[GenerationStep],
                      language: str = "python") -> ChainResult:
        """Execute a chain of generation steps."""
        result = ChainResult(success=False, steps_total=len(steps))
        accumulated_context = ""
        completed = 0
        failed = 0
        repairs = 0

        for step in steps:
            step.context = accumulated_context
            generated = self._execute_step(step, language)

            if generated:
                if self._validate_fragment(generated, language):
                    step.generated = generated
                    step.validated = True
                    accumulated_context += "\n" + generated
                    completed += 1
                    result.fragments.append(generated)
                else:
                    repaired, repair_count = self._auto_repair(step, generated, language)
                    repairs += repair_count
                    if repaired:
                        step.generated = repaired
                        step.validated = True
                        accumulated_context += "\n" + repaired
                        completed += 1
                        result.fragments.append(repaired)
                    else:
                        failed += 1
                        logger.warning(
                            "SmartPromptChain: Step %d (%s) failed after %d repairs",
                            step.step_id, step.step_type, repair_count,
                        )
                        result.fragments.append(generated)
                        accumulated_context += "\n" + generated
            else:
                failed += 1
                step.attempts += 1

        result.steps_completed = completed
        result.steps_failed = failed
        result.repair_count = repairs
        result.code = "\n".join(result.fragments)
        result.success = failed == 0 or completed > 0
        return result
