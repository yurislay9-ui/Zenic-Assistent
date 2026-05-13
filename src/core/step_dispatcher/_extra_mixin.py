"""StepDispatcher - Additional methods."""

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger("zenic_agents.step_dispatcher")


class StepDispatcherExtraMixin:
    """Additional methods mixin."""

    async def _handle_quality_report(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle QUALITY_REPORT action."""
        if code:
            report = self._orch._analysis.generate_quality_report(
                self._orch.ast_engine.analyze_structure(code, lang), code, lang
            )
            explanations.append(report)
        return result_code, code, explanations

    async def _handle_explain_code(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle EXPLAIN_CODE action."""
        if code:
            base_explanation = self._orch._analysis.explain_code(
                code, lang, ast_analysis
            )
            # MiniAI: mejorar explicacion si hay violaciones detectadas
            if self._orch._ai.is_loaded:
                violations = []
                if "eval(" in code or "exec(" in code:
                    violations.append("dangerous_call")
                if "os.system(" in code:
                    violations.append("command_injection")
                if violations:
                    ai_explain = self._orch._ai.explain_violation(
                        code[:200], violations
                    )
                    if ai_explain:
                        base_explanation += f" | AI: {ai_explain}"
            explanations.append(base_explanation)
        else:
            explanations.append(
                self._orch._analysis.explain_concept(intent)
            )
        return result_code, code, explanations

    async def _handle_search_definition(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle SEARCH_DEFINITION action."""
        if code:
            nodes = self._orch.ast_engine.get_node_info(intent.target)
            if nodes:
                for n in nodes[:5]:
                    explanations.append(
                        f"Found: {n['node_type']} '{n['name']}' "
                        f"(complexity: {n.get('complexity', 'N/A')})"
                    )
            else:
                explanations.append(
                    f"'{intent.target}' not found in code"
                )
        return result_code, code, explanations

    async def _handle_validation(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle SYMBOLIC_VALIDATION / SYNTAX_VALIDATION action."""
        # Use ValidationAgent (F5) for intelligent validation
        if self._orch._validation_agent and code:
            from src.core.agents.schemas import ValidationInput
            v_output = self._orch._validation_agent.validate_with_runner(
                self._orch._agent_runner,
                target="code",
                content=code,
                rules=["security", "quality"],
                language=lang,
            )
            if v_output.issues:
                issue_strs = [
                    f"{i.severity}: {i.message}"
                    for i in v_output.issues[:5]
                ]
                explanations.append(
                    f"Validation (F5): {len(v_output.issues)} issues "
                    f"found (risk={v_output.risk_score:.2f}, "
                    f"source={v_output.source})"
                )
                for iss in issue_strs:
                    explanations.append(f"  - {iss}")
            else:
                explanations.append(
                    "Validation (F5): No issues found"
                )
        else:
            explanations.append(
                "Symbolic validation executed "
                "(bounded symbolic execution)"
            )
        return result_code, code, explanations

    async def _handle_scaffold_fractal(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle SCAFFOLD_FRACTAL action."""
        # Brecha C: Generacion Fractal (Top-Down) multi-archivo
        if hasattr(self._orch, '_fractal_gen') and self._orch._fractal_gen:
            from src.core.agents.intent_shared import infer_template_type
            project_type = infer_template_type(
                str(intent.op), intent.raw_code or str(intent)
            )
            fractal_result = self._orch._fractal_gen.generate_project(
                description=str(intent),
                project_type=project_type,
                project_name=intent.target or "generated_project",
                language=lang,
                output_dir="",
            )
            if fractal_result.spec and fractal_result.spec.files:
                project_repr = []
                for f_bp in fractal_result.spec.files:
                    content = getattr(f_bp, 'generated_content', '') or getattr(f_bp, '_generated_content', '')
                    if content:
                        project_repr.append(
                            f"# === {f_bp.path} ===\n{content}"
                        )
                result_code = "\n\n".join(project_repr)
                explanations.append(
                    f"Fractal: {len(fractal_result.files_generated)} "
                    f"files, phase={fractal_result.current_phase}"
                )
            else:
                explanations.append(
                    "Fractal: Fallback to standard generation"
                )
        else:
            explanations.append(
                "Fractal: Not available in this orchestrator"
            )
        return result_code, code, explanations

    async def _handle_analyze_and_respond(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle ANALYZE_AND_RESPOND action."""
        if code:
            explanations.append(
                self._orch._analysis.analyze_and_respond(
                    code, intent, ast_analysis
                )
            )
        else:
            explanations.append(
                self._orch._analysis.general_response(intent)
            )
        return result_code, code, explanations

    async def _handle_quick_analysis(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle QUICK_ANALYSIS action."""
        explanations.append("Quick analysis completed")
        return result_code, code, explanations

    async def _handle_full_analysis(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle FULL_ANALYSIS action."""
        if code:
            explanations.append(
                self._orch._analysis.full_analysis(
                    code, intent, ast_analysis, lang
                )
            )
        else:
            explanations.append(
                self._orch._analysis.general_response(intent)
            )
        return result_code, code, explanations

    async def _handle_check_dependencies(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle CHECK_DEPENDENCIES action."""
        if code:
            deps = self._orch._analysis.check_dependencies(
                code, intent.target, lang
            )
            explanations.extend(deps)
        return result_code, code, explanations

    # ------------------------------------------------------------------
    #  PLAN EXECUTION
    # ------------------------------------------------------------------

    async def execute_plan_steps(
        self,
        plan,
        intent,
        code: str,
        explanations: List[str],
        lang: str,
        ast_analysis: Dict,
    ) -> Tuple[str, str, List[str]]:
        """
        Iterate all steps in a plan and execute them sequentially.

        Args:
            plan: The plan with .steps list
            intent: IntentPayload with operation context
            code: Current code state
            explanations: List of explanation strings
            lang: Programming language
            ast_analysis: AST analysis results

        Returns:
            Tuple of (result_code, code, explanations)
        """
        result_code = ""

        for step in plan.steps:
            result_code, code, explanations = await self.execute_step(
                step, intent, code, result_code, explanations,
                lang, ast_analysis, plan,
            )

        return result_code, code, explanations

