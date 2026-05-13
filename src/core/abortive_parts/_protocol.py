"""
AbortiveProtocol handle_abortive_protocol method mixin.
"""

import time
import logging

from ._imports import (
    gc, logger,
    MAX_SUBTASKS, MAX_ABORTIVE_DEPTH,
    ABORTIVE_SANDBOX_TTL_MULTIPLIER, ABORTIVE_SANDBOX_TTL_MIN,
    get_solver_timeout_ms, get_projects_dir,
)


class ProtocolMixin:
    """Main abortive protocol handler mixin."""

    async def handle_abortive_protocol(self, intent, routing, plan, ast_analysis, start_time):
        """
        Protocolo Abortivo del documento de arquitectura (Gap 4 Fix):

        Si el solver hace timeout (15s), el sistema:
        1. Hace rollback al estado pristino anterior
        2. Subdivide automaticamente la tarea en unidades logicas
        3. EJECUTA cada subtask a traves del pipeline completo (no solo plan)
        4. Combina los resultados de cada subtask
        5. Valida el resultado combinado en sandbox
        6. Si pasa -> commit SUCCESS; si subtask timeout -> subdividir recursivamente (max depth 2)
        7. Si la combinacion falla -> devolver Razonamiento Parcial con token de resumption
        """
        orch = self._orchestrator
        logger.warning("PROTOCOLO ABORTIVO activado para: %s", intent.target)

        # Crear workspace AISLADO para el protocolo abortivo
        abortive_workspace = orch._isolation_manager.create_workspace(
            ttl_seconds=max(orch.sandbox.timeout_seconds * ABORTIVE_SANDBOX_TTL_MULTIPLIER, ABORTIVE_SANDBOX_TTL_MIN)
        )

        # Rollback
        p_dir = str(get_projects_dir())
        orch.ledger.rollback(intent.target, p_dir, workspace=abortive_workspace)

        solver_timeout = plan.solver_proof.get("timeout_ms", get_solver_timeout_ms(orch.settings)) if plan.solver_proof else get_solver_timeout_ms(orch.settings)

        # Generar subtareas automaticamente (limit to 5 for memory safety)
        subtasks = self.generate_subtasks(intent, ast_analysis, plan)[:MAX_SUBTASKS]

        # EJECUTAR cada subtask a traves del pipeline completo
        subtask_results = []
        for i, subtask_msg in enumerate(subtasks):
            try:
                result = await self.execute_subtask(subtask_msg, depth=0, max_depth=MAX_ABORTIVE_DEPTH)
                subtask_results.append(result)
            except Exception as e:
                logger.error("Subtask %d failed: %s", i, e)
                subtask_results.append({
                    "subtask": subtask_msg,
                    "status": "ERROR",
                    "code": "",
                    "message": str(e),
                })

        # Recoger gc tras operaciones pesadas
        gc.collect()

        # Combinar resultados de subtasks
        combined_code = self.merge_subtask_results(subtask_results, intent.language)

        if combined_code:
            # Validar resultado combinado en sandbox
            orch.ledger.snapshot(intent.target, p_dir, workspace=abortive_workspace)
            trial = await orch.sandbox.validate_code(combined_code, intent.language, intent.target)

            if trial.status == "PASS" and combined_code:
                # Commit resultado combinado en workspace aislado
                node = orch.ledger.commit(intent.target, combined_code, p_dir,
                                           workspace=abortive_workspace)
                # Release sandbox workspace after successful commit
                try:
                    orch._isolation_manager.release_workspace(abortive_workspace.sandbox_id)
                except Exception:
                    pass
                orch.cache.save(intent, "PROVEN",
                              {"h": node.hash_sha256[:8], "code": combined_code},
                              combined_code, intent.language)
                elapsed = int((time.time() - start_time) * 1000)
                orch._analysis.log_request(intent, "ABORTIVE_SUCCESS", elapsed,
                                solver_status="TIMEOUT_SUBDIVIDE_REQUIRED")
                return {
                    "status": "SUCCESS", "code": combined_code,
                    "hash": node.hash_sha256[:12], "error": "",
                    "processing_time_ms": elapsed,
                    "route": routing.route,
                    "criticality": routing.criticality,
                    "solver_status": "ABORTIVE_RESOLVED",
                    "solver_proof": plan.solver_proof,
                    "mcts_simulations": plan.mcts_simulations,
                    "mcts_depth_reached": plan.mcts_depth_reached,
                    "ast_analysis": ast_analysis,
                    "explanations": [
                        f"Protocolo Abortivo: Solver timeout ({solver_timeout}ms) para '{intent.target}'.",
                        f"Tarea subdividida y ejecutada en {len(subtasks)} subtareas.",
                        f"Resultado combinado valido (sandbox PASS).",
                    ],
                    "subtasks": subtask_results,
                    "warnings": trial.warnings,
                    "metrics": trial.metrics,
                    "paths_explored": trial.paths_explored,
                    "paths_pruned": trial.paths_pruned,
                }
            elif trial.status == "FAIL_K_PATH":
                # K-Path exceeded -> rollback + partial reasoning with resumption
                orch.ledger.rollback(intent.target, p_dir, workspace=abortive_workspace)
                orch._isolation_manager.release_workspace(abortive_workspace.sandbox_id)
                elapsed = int((time.time() - start_time) * 1000)
                return orch._partial_reasoning.build_partial_reasoning_response(
                    intent, routing, plan, ast_analysis, trial, start_time,
                    subtask_results=subtask_results, combined_code=combined_code
                )
            else:
                # Other failure -> rollback + partial reasoning with resumption
                orch.ledger.rollback(intent.target, p_dir, workspace=abortive_workspace)
                orch._isolation_manager.release_workspace(abortive_workspace.sandbox_id)
                elapsed = int((time.time() - start_time) * 1000)
                # Build a synthetic SandboxResult for the partial reasoning response
                from src.core.shared.contracts import SandboxResult
                trial_for_partial = SandboxResult(
                    status="FAIL",
                    error_message=trial.error_message if hasattr(trial, 'error_message') else "Sandbox validation failed",
                    warnings=trial.warnings if hasattr(trial, 'warnings') else [],
                    paths_explored=trial.paths_explored if hasattr(trial, 'paths_explored') else 0,
                    paths_pruned=trial.paths_pruned if hasattr(trial, 'paths_pruned') else 0,
                )
                return orch._partial_reasoning.build_partial_reasoning_response(
                    intent, routing, plan, ast_analysis, trial_for_partial, start_time,
                    subtask_results=subtask_results, combined_code=combined_code
                )

        # No combined code could be produced — release workspace before returning
        orch._isolation_manager.release_workspace(abortive_workspace.sandbox_id)
        elapsed = int((time.time() - start_time) * 1000)
        from src.core.shared.contracts import SandboxResult
        no_code_trial = SandboxResult(
            status="FAIL",
            error_message="No code produced by any subtask",
            warnings=[],
            paths_explored=0,
            paths_pruned=0,
        )
        return orch._partial_reasoning.build_partial_reasoning_response(
            intent, routing, plan, ast_analysis, no_code_trial, start_time,
            subtask_results=subtask_results, combined_code=""
        )
