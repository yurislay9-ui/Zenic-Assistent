"""
Backward compatibility delegation mixin for BaseOrchestrator.
"""


class CompatMixin:
    """Backward compatibility - delegate old method names to sub-objects."""

    # Abortive Protocol backward compat
    async def _handle_abortive_protocol(self, intent, routing, plan, ast_analysis, start_time):
        return await self._abortive.handle_abortive_protocol(
            intent, routing, plan, ast_analysis, start_time
        )

    def _generate_subtasks(self, intent, ast_analysis, plan=None):
        return self._abortive.generate_subtasks(intent, ast_analysis, plan)

    async def _execute_subtask(self, subtask, depth=0, max_depth=2):
        return await self._abortive.execute_subtask(subtask, depth, max_depth)

    def _merge_subtask_results(self, subtask_results, language="python"):
        return self._abortive.merge_subtask_results(subtask_results, language)

    def _merge_python_code(self, code_parts):
        return self._abortive.merge_python_code(code_parts)

    def _merge_go_code(self, code_parts):
        return self._abortive.merge_go_code(code_parts)

    def _merge_block_code(self, code_parts, comment_prefix, skip_prefix):
        return self._abortive.merge_block_code(
            code_parts, comment_prefix, skip_prefix
        )

    # Partial Reasoning backward compat
    def _build_partial_reasoning_response(self, intent, routing, plan,
                                           ast_analysis, trial, start_time,
                                           subtask_results=None,
                                           combined_code=""):
        return self._partial_reasoning.build_partial_reasoning_response(
            intent, routing, plan, ast_analysis, trial, start_time,
            subtask_results=subtask_results, combined_code=combined_code,
        )

    # Code Generator backward compat
    def _generate_intelligent_code(self, intent, ast_analysis, lang):
        return self._code_gen.generate_intelligent_code(intent, ast_analysis, lang)

    def _extract_solver_insights(self, solver_proof):
        return self._code_gen.extract_solver_insights(solver_proof)

    def _extract_ast_context(self, ast_analysis):
        return self._code_gen.extract_ast_context(ast_analysis)

    def _extract_symbolic_insights(self, sandbox_result):
        return self._code_gen.extract_symbolic_insights(sandbox_result)

    def _generate_pipeline_driven_code(self, intent, ast_analysis, plan, lang):
        return self._code_gen.generate_pipeline_driven_code(
            intent, ast_analysis, plan, lang
        )

    def _generate_python_pipeline_driven(self, intent, ast_analysis, ast_context,
                                          solver_insights, mcts_actions, safe_target,
                                          has_security_action, has_replace_node,
                                          has_patch_fix):
        return self._code_gen.generate_python_pipeline_driven(
            intent, ast_analysis, ast_context, solver_insights,
            mcts_actions, safe_target, has_security_action,
            has_replace_node, has_patch_fix,
        )

    def _generate_pipeline_feature_module(self, safe_target, existing_functions,
                                           existing_classes, needed_imports,
                                           solver_insights, mcts_actions):
        return self._code_gen.generate_pipeline_feature_module(
            safe_target, existing_functions, existing_classes,
            needed_imports, solver_insights, mcts_actions,
        )

    def _generate_contextual_code(self, intent, ast_analysis, plan, lang):
        return self._code_gen.generate_contextual_code(
            intent, ast_analysis, plan, lang
        )

    def _generate_python_contextual(self, intent, ast_analysis, safe_target,
                                     existing_functions, existing_classes,
                                     existing_connections, needed_imports,
                                     max_complexity):
        return self._code_gen.generate_python_contextual(
            intent, ast_analysis, safe_target, existing_functions,
            existing_classes, existing_connections, needed_imports,
            max_complexity,
        )

    def _generate_security_module(self, safe_target):
        return self._code_gen.generate_security_module(safe_target)

    def _generate_feature_module(self, safe_target, existing_functions,
                                  existing_classes, needed_imports):
        return self._code_gen.generate_feature_module(
            safe_target, existing_functions, existing_classes, needed_imports,
        )

    def _generate_kotlin_contextual(self, intent, safe_target, existing_classes):
        return self._code_gen.generate_kotlin_contextual(
            intent, safe_target, existing_classes,
        )

    def _generate_go_contextual(self, intent, safe_target):
        return self._code_gen.generate_go_contextual(intent, safe_target)

    def _generate_javascript_contextual(self, intent, safe_target):
        return self._code_gen.generate_javascript_contextual(intent, safe_target)

    # Code Transformer backward compat
    def _refactor_python(self, code, ast_analysis, solver_insights=None):
        return self._code_transform.refactor_python(code, ast_analysis, solver_insights)

    def _fix_python(self, code, ast_analysis, solver_insights=None):
        return self._code_transform.fix_python(code, ast_analysis, solver_insights)

    def _optimize_function(self, target_name, lang="python",
                            ast_analysis=None, solver_insights=None):
        return self._code_transform.optimize_function(
            target_name, lang, ast_analysis, solver_insights,
        )

    # Analysis Utils backward compat
    def _apply_fix(self, code, intent, lang):
        return self._analysis.apply_fix(code, intent, lang)

    def _generate_quality_report(self, analysis, code, lang):
        return self._analysis.generate_quality_report(analysis, code, lang)

    def _explain_code(self, code, lang, ast_analysis):
        return self._analysis.explain_code(code, lang, ast_analysis)

    def _explain_concept(self, intent):
        return self._analysis.explain_concept(intent)

    def _analyze_and_respond(self, code, intent, ast_analysis):
        return self._analysis.analyze_and_respond(code, intent, ast_analysis)

    def _general_response(self, intent):
        return self._analysis.general_response(intent)

    def _full_analysis(self, code, intent, ast_analysis, lang):
        return self._analysis.full_analysis(code, intent, ast_analysis, lang)

    def _check_dependencies(self, code, target, lang):
        return self._analysis.check_dependencies(code, target, lang)

    def _log_request(self, intent, status, elapsed_ms, cache_hit=False,
                    solver_status="", mcts_sims=0):
        return self._analysis.log_request(
            intent, status, elapsed_ms, cache_hit, solver_status, mcts_sims,
        )

    # Shared Properties

    @property
    def model_manager(self):
        """Public accessor for model manager."""
        return getattr(self, '_model_mgr', None)

    @property
    def low_power_mode(self):
        """Public accessor for low power mode."""
        return getattr(self, '_low_power_mode', None)

    @property
    def context_pointer_engine(self):
        """Public accessor for context pointer engine."""
        return getattr(self, '_context_pointer_engine', None)

    def get_niche_cron(self):
        """Public accessor for niche cron scheduler."""
        return getattr(self, '_niche_cron', None)

    def get_niche_auto_scraper(self):
        """Public accessor for niche auto scraper."""
        return getattr(self, '_niche_auto_scraper', None)

    @property
    def abortive(self):
        """Public accessor for abortive protocol."""
        return getattr(self, '_abortive', None)

    @property
    def pending_resumptions(self):
        """Public accessor for pending resumptions dict."""
        return getattr(self, '_pending_resumptions', {})

    @property
    def isolation_manager(self):
        """Public accessor for isolation manager."""
        return getattr(self, '_isolation_manager', None)
