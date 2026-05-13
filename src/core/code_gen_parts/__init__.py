"""
CodeGenerator — facade re-exporting all sub-modules.

Backward-compatible: ``from src.core.code_generator import CodeGenerator``
still works exactly as before.

New in this version:
  - CodeAssemblerMixin: assembles REAL code from Jinja2 templates
  - SmartPromptChainMixin: fragmented generation for small LLMs
  - ExecutionBridgeMixin: validates generated code by executing it
"""

from typing import Optional, Dict, List

from ._extractors_mixin import ExtractorsMixin
from ._pipeline_mixin import PipelineMixin
from ._contextual_mixin import ContextualMixin
from .assembler import CodeAssembler
from .smart_chain import SmartPromptChain
from ._exec_bridge_mixin import ExecutionBridge


class CodeGenerator(ExtractorsMixin, PipelineMixin, ContextualMixin):
    """Generates code using pipeline intelligence (AST + Solver + MCTS).

    Enhanced with CodeAssembler for REAL code generation from templates,
    SmartPromptChain for fragmented LLM generation, and ExecutionBridge
    for validation by execution.
    """

    def __init__(self, orchestrator=None, template_engine=None, llm_engine=None):
        self._orchestrator = orchestrator
        self._assembler = CodeAssembler(template_engine=template_engine)
        self._smart_chain = SmartPromptChain(llm_engine=llm_engine)
        self._exec_bridge = ExecutionBridge(code_agent=self)

    def generate_real_code(self, description: str, niche_plan=None,
                           entities: Optional[list] = None,
                           project_name: str = "zenic_app") -> dict:
        """Generate a REAL project with functional code (not stubs).

        This is the new primary API that replaces stub generation.

        Args:
            description: What the user wants to build
            niche_plan: Optional CompositionPlan from NicheLoader
            entities: List of entity dicts from niche YAML
            project_name: Name for the generated project

        Returns:
            Dict with 'files' (filename→content), 'validation', 'blocks'
        """
        # 1. Assemble project from real templates
        files = self._assembler.assemble_project(
            description, niche_plan, project_name, entities
        )

        # 2. For each entity, generate real _process() methods
        if entities:
            for entity in entities:
                entity_name = entity.get("name", "Item")
                process_code = self._assembler.build_service_method(
                    entity, operation="crud"
                )
                files[f"blocks/{entity_name.lower()}_process.py"] = process_code

        # 3. Validate generated code
        validation_results = {}
        for filename, content in files.items():
            if filename.endswith(".py") and len(content) > 50:
                result = self._exec_bridge.validate_code(
                    content,
                    module_name=filename.replace("/", "_").replace(".py", ""),
                    expected_classes=[],  # We don't know class names a priori
                )
                validation_results[filename] = {
                    "valid": result.valid,
                    "syntax_ok": result.syntax_ok,
                    "errors": result.errors[:3],  # Truncate for readability
                }

        # 4. Resolve blocks used
        blocks = self._assembler.resolve_blocks(description, niche_plan)

        return {
            "files": files,
            "validation": validation_results,
            "blocks": blocks,
            "project_name": project_name,
            "total_files": len(files),
        }

    def generate_fragmented(self, task_description: str, language: str = "python",
                            entity_info: Optional[dict] = None) -> dict:
        """Generate code using SmartPromptChain (fragmented for small LLMs).

        Args:
            task_description: What to generate
            language: Target language
            entity_info: Optional entity dict

        Returns:
            Dict with 'code', 'steps_completed', 'success'
        """
        result = self._smart_chain.generate_code(
            task_description, language, entity_info
        )

        return {
            "code": result.code,
            "success": result.success,
            "steps_total": result.steps_total,
            "steps_completed": result.steps_completed,
            "steps_failed": result.steps_failed,
            "repair_count": result.repair_count,
        }


__all__ = [
    "CodeGenerator",
    "CodeAssembler",
    "SmartPromptChain",
    "ExecutionBridge",
]
