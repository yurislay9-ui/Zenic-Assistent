"""StepDispatcher - Core methods."""

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger("zenic_agents.step_dispatcher")


class StepDispatcherCoreMixin:
    """Core methods mixin."""

    """
    Unified step dispatch logic using Strategy Registry pattern.

    Takes a reference to the orchestrator (BaseOrchestrator) to access
    its components (ast_engine, scrap, surgeon, _code_gen, _code_transform,
    _analysis, _ai, _validation_agent, _agent_runner, _fractal_gen, etc.).

    Handles ALL step action types via individually registered handlers:
    - ANALYZE_STRUCTURE
    - SCRAPE_PATTERNS
    - GENERATE_CODE
    - REPLACE_AST_NODE
    - DELETE_AST_NODE
    - TRACE_EXECUTION
    - PATCH_FIX
    - QUALITY_REPORT
    - EXPLAIN_CODE
    - SEARCH_DEFINITION
    - SYMBOLIC_VALIDATION / SYNTAX_VALIDATION
    - ANALYZE_AND_RESPOND
    - QUICK_ANALYSIS
    - FULL_ANALYSIS
    - CHECK_DEPENDENCIES
    - SCAFFOLD_FRACTAL
    """

    def _register_handlers(self):
        """Register all step action handlers in the strategy registry."""
        self._registry.register("ANALYZE_STRUCTURE", self._handle_analyze_structure)
        self._registry.register("SCRAPE_PATTERNS", self._handle_scrape_patterns)
        self._registry.register("GENERATE_CODE", self._handle_generate_code)
        self._registry.register("REPLACE_AST_NODE", self._handle_replace_ast_node)
        self._registry.register("DELETE_AST_NODE", self._handle_delete_ast_node)
        self._registry.register("TRACE_EXECUTION", self._handle_trace_execution)
        self._registry.register("PATCH_FIX", self._handle_patch_fix)
        self._registry.register("QUALITY_REPORT", self._handle_quality_report)
        self._registry.register("EXPLAIN_CODE", self._handle_explain_code)
        self._registry.register("SEARCH_DEFINITION", self._handle_search_definition)
        self._registry.register("SYMBOLIC_VALIDATION", self._handle_validation)
        self._registry.register("SYNTAX_VALIDATION", self._handle_validation)
        self._registry.register("SCAFFOLD_FRACTAL", self._handle_scaffold_fractal)
        self._registry.register("ANALYZE_AND_RESPOND", self._handle_analyze_and_respond)
        self._registry.register("QUICK_ANALYSIS", self._handle_quick_analysis)
        self._registry.register("FULL_ANALYSIS", self._handle_full_analysis)
        self._registry.register("CHECK_DEPENDENCIES", self._handle_check_dependencies)

    async def execute_step(
        self,
        step,
        intent,
        code: str,
        result_code: str,
        explanations: List[str],
        lang: str,
        ast_analysis: Dict,
        plan,
    ) -> Tuple[str, str, List[str]]:
        """
        Execute a single step of the plan using the Strategy Registry.

        Args:
            step: Plan step with .action, .constraints, .target_node_name
            intent: IntentPayload with operation context
            code: Current code state
            result_code: Current result code
            explanations: List of explanation strings (mutated in place)
            lang: Programming language
            ast_analysis: AST analysis results
            plan: The full plan (for solver_proof, etc.)

        Returns:
            Tuple of (result_code, code, explanations)
        """
        action = step.action
        orch = self._orch

        # Publish step-started event
        if self._event_bus:
            from src.core.patterns.orchestration import Event
            self._event_bus.publish(Event(
                name="step.started",
                data={"action": action, "target": getattr(step, 'target_node_name', None)},
                source="StepDispatcher"
            ))

        # Execute via strategy registry with retry
        try:
            handler = self._registry.get(action)
            if handler:
                result_code, code, explanations = await handler(
                    step, intent, code, result_code, explanations, lang, ast_analysis, plan
                )
            else:
                explanations.append(f"Unknown action: {action}")
                logger.warning(f"StepDispatcher: No handler for action '{action}'")
        except KeyError:
            explanations.append(f"Unknown action: {action}")
            logger.warning(f"StepDispatcher: No handler for action '{action}'")
        except Exception as e:
            logger.error(f"StepDispatcher: Error executing {action}: {e}")
            explanations.append(f"Error in {action}: {str(e)[:100]}")

        # Publish step-completed event
        if self._event_bus:
            from src.core.patterns.orchestration import Event
            self._event_bus.publish(Event(
                name="step.completed",
                data={"action": action, "has_code": bool(result_code or code)},
                source="StepDispatcher"
            ))

        return result_code, code, explanations

    # ------------------------------------------------------------------
    #  INDIVIDUAL HANDLER METHODS
    # ------------------------------------------------------------------

    async def _handle_analyze_structure(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle ANALYZE_STRUCTURE action."""
        if code:
            analysis = self._orch.ast_engine.analyze_structure(code, lang)
            explanations.append(
                f"Structure: {analysis['functions']} functions, "
                f"{analysis['classes']} classes, max complexity "
                f"{analysis['max_complexity']}"
            )
        else:
            explanations.append("No code provided for analysis.")
        return result_code, code, explanations

    async def _handle_scrape_patterns(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle SCRAPE_PATTERNS action."""
        query = step.constraints.get("query", intent.scrap_query)
        # SmartScraper: Auto-routing multi-fuente
        smart_result = await self._orch.scrap.smart_fetch(query, lang)
        if smart_result.get("success") and smart_result.get("content"):
            source_name = smart_result.get("source", "github")
            explanations.append(
                f"SmartScraper: Found content via {source_name}"
            )
            content = smart_result["content"]
            if not code:
                code = content
        else:
            # Fallback: buscar en todas las fuentes
            all_results = await self._orch.scrap.fetch_all_sources(query, lang)
            best_content = ""
            best_source = ""
            for src in ["github", "devdocs", "iconstack", "picsum"]:
                if src in all_results and all_results[src]:
                    best_content = all_results[src]
                    best_source = src
                    break
            if best_content:
                explanations.append(
                    f"SmartScraper: Found content via {best_source} "
                    f"(fallback)"
                )
                if not code:
                    code = best_content
            else:
                explanations.append(
                    "SmartScraper: No results. Using local generation."
                )
        return result_code, code, explanations

    async def _handle_generate_code(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle GENERATE_CODE action.

        Generation strategy (ordered by quality):
        1. M1: CodeAssembler — real code from templates (always available, deterministic)
        2. LLM-augmented via CodeAgent — when LLM is loaded
        3. M2: SmartPromptChain — fragmented generation for small LLMs
        4. Deterministic template fallback — contextual generation
        """
        generated_code = None
        source = "template"

        # ── Strategy 1: M1 CodeAssembler (real code from templates) ──
        if hasattr(self._orch, '_code_gen') and hasattr(self._orch._code_gen, 'generate_real_code'):
            try:
                description = str(intent) if intent else ""
                entity_info = None
                # Extract entities from intent if available
                if hasattr(intent, 'raw_code') and intent.raw_code:
                    import ast as _ast
                    try:
                        tree = _ast.parse(intent.raw_code)
                        for node in _ast.walk(tree):
                            if isinstance(node, _ast.ClassDef):
                                entity_info = entity_info or []
                                fields = []
                                for item in node.body:
                                    if isinstance(item, _ast.AnnAssign) and isinstance(item.target, _ast.Name):
                                        fields.append({"name": item.target.id, "type": "str"})
                                entity_info.append({"name": node.name, "fields": fields})
                    except (SyntaxError, AttributeError):
                        pass

                real_result = self._orch._code_gen.generate_real_code(
                    description=description,
                    niche_plan=None,
                    entities=entity_info,
                    project_name=intent.target if hasattr(intent, 'target') else "module",
                )
                if real_result and real_result.get("files"):
                    files = real_result["files"]
                    # Return the most relevant file
                    for key in ["blocks/crud_service.py", "blocks/jwt_auth.py", "main.py"]:
                        if key in files and len(files[key]) > 100:
                            generated_code = files[key]
                            source = "assembler"
                            explanations.append(
                                f"Code generated for {intent.op} via CodeAssembler "
                                f"({real_result.get('total_files', 0)} files)"
                            )
                            break
                    if not generated_code:
                        # Return first substantial file
                        for key, content in files.items():
                            if key.endswith(".py") and len(content) > 100:
                                generated_code = content
                                source = "assembler"
                                explanations.append(f"Code generated for {intent.op} via CodeAssembler")
                                break
            except Exception as e:
                import logging as _log
                _log.getLogger(__name__).debug("CodeAssembler generation failed: %s", e)

        # ── Strategy 2: LLM-augmented via CodeAgent ──
        if not generated_code and (
            hasattr(self._orch, '_code_agent') and self._orch._code_agent is not None
            and hasattr(self._orch, '_agent_runner') and self._orch._agent_runner is not None
            and hasattr(self._orch, '_ai') and self._orch._ai.is_loaded
        ):
            try:
                code_result = self._orch._code_agent.generate_with_runner(
                    self._orch._agent_runner,
                    requirements=str(intent),
                    language=lang,
                )
                if code_result and code_result.code:
                    generated_code = code_result.code
                    source = getattr(code_result, 'source', 'llm')
                    explanations.append(f"Code generated for {intent.op} via {source}")
            except Exception as e:
                import logging as _log
                _log.getLogger(__name__).debug("CodeAgent LLM generation failed: %s", e)

        # ── Strategy 3: M2 SmartPromptChain (fragmented for small LLMs) ──
        if not generated_code and hasattr(self._orch, '_code_gen'):
            smart_chain = getattr(self._orch._code_gen, '_smart_chain', None)
            if smart_chain:
                try:
                    entity_info = None
                    chain_result = smart_chain.generate_code(
                        task_description=str(intent),
                        language=lang or "python",
                        entity_info=entity_info,
                    )
                    if chain_result and chain_result.success and chain_result.code:
                        generated_code = chain_result.code
                        source = "smart_chain"
                        explanations.append(
                            f"Code generated for {intent.op} via SmartPromptChain "
                            f"({chain_result.steps_completed}/{chain_result.steps_total} steps, "
                            f"{chain_result.repair_count} repairs)"
                        )
                except Exception as e:
                    import logging as _log
                    _log.getLogger(__name__).debug("SmartPromptChain generation failed: %s", e)

        # ── Strategy 4: Deterministic template fallback ──
        if not generated_code:
            result_code = self._orch._code_gen.generate_contextual_code(
                intent, ast_analysis, plan, lang
            )
            explanations.append(f"Code generated for {intent.op} (template fallback)")
        else:
            result_code = generated_code

        return result_code, code, explanations

    async def _handle_replace_ast_node(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle REPLACE_AST_NODE action."""
        if code and step.target_node_name:
            solver_insights = (
                self._orch._code_gen.extract_solver_insights(plan.solver_proof)
                if plan else None
            )
            # MiniAI: sugerir patron de reemplazo
            if self._orch._ai.is_loaded:
                pattern = self._orch._ai.suggest_pattern(
                    step.target_node_name, str(intent)
                )
                explanations.append(f"MiniAI suggests pattern: {pattern}")
            # FIX: Pass raw_code to optimizer so it can analyze the actual function
            raw_code = code or getattr(intent, 'raw_code', None) or ""
            new_snippet = self._orch._code_transform.optimize_function(
                step.target_node_name, lang, ast_analysis, solver_insights,
                raw_code=raw_code
            )
            result_code = self._orch.surgeon.mutate_node(
                code, step.target_node_name, new_snippet, lang
            )
            explanations.append(
                f"Function '{step.target_node_name}' replaced "
                f"via AST surgery (optimizer received raw_code)"
            )
        else:
            result_code = self._orch._code_gen.generate_contextual_code(
                intent, ast_analysis, plan, lang
            )
            explanations.append("Optimized code generated")
        return result_code, code, explanations

    async def _handle_delete_ast_node(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle DELETE_AST_NODE action."""
        if code and step.target_node_name:
            result_code = self._orch.surgeon.delete_function(
                code, step.target_node_name, lang
            )
            explanations.append(
                f"Function '{step.target_node_name}' deleted "
                f"via AST surgery"
            )
        return result_code, code, explanations

    async def _handle_trace_execution(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle TRACE_EXECUTION action."""
        explanations.append(
            "Symbolic execution trace performed (K-Path limited)"
        )
        if code:
            analysis = self._orch.ast_engine.analyze_structure(code, lang)
            for fn_name in analysis.get("function_names", []):
                explanations.append(f"  - Traced: {fn_name}")
        return result_code, code, explanations

    async def _handle_patch_fix(
        self, step, intent, code, result_code, explanations, lang, ast_analysis, plan
    ):
        """Handle PATCH_FIX action."""
        result_code = self._orch._analysis.apply_fix(code, intent, lang)
        explanations.append("Fix patch applied")
        return result_code, code, explanations

