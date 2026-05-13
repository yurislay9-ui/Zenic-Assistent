"""Mixin: Build partial reasoning response for PartialReasoningManager."""

import json
import time
import uuid

from ._imports import SubtaskDescriptor


class PartialMixin:
    """Mixin providing partial reasoning response construction."""

    def build_partial_reasoning_response(self, intent, routing, plan, ast_analysis, trial, start_time,
                                          subtask_results=None, combined_code=""):
        """
        Construye la respuesta de Razonamiento Parcial como especifica el documento.
        (Gap 5 Fix): Now includes resumption_token and state for resume_from_partial().

        Devuelve un payload JSON con:
        - Mensaje explicativo del estado
        - tool_calls con zenith_mcts_plan para subdivision
        - resumption token para reanudar ejecucion parcial
        - Metadata del solver, K-Paths, y hash estructural
        """
        orch = self._orchestrator
        elapsed = int((time.time() - start_time) * 1000)
        k_path_eval = trial.paths_explored
        k_path_limit = orch.sandbox.k_path_limit

        # Generar subtareas para el tool_call
        subtasks = orch._abortive.generate_subtasks(intent, ast_analysis, plan)

        subtask_1 = "Levantamiento algoritmico de interfaces genericas de aislamiento (Mock Boundaries)."
        subtask_2 = "Despliegue quirurgico condicionado de la logica central evaluado independientemente."

        if len(subtasks) >= 2:
            subtask_1 = subtasks[0].message if isinstance(subtasks[0], SubtaskDescriptor) else str(subtasks[0])
            subtask_2 = subtasks[1].message if isinstance(subtasks[1], SubtaskDescriptor) else str(subtasks[1])

        # Construir el mensaje de razonamiento parcial
        solver_type = "Z3" if plan.solver_proof and plan.solver_proof.get("solver_type") == "Z3" else "SMT"
        content = (
            f"Analisis Estructural (Nivel 4 | Reflexion Sandbox): "
            f"La mutacion exigida cruza el umbral de seguridad matematica "
            f"(Demostracion interrumpida por {solver_type} Solver timeout). "
            f"El mapeo profundo AST infiere que este injerto impacta sobre "
            f"{k_path_eval} rutas perimetricas criticas "
            f"(K-Paths eval={k_path_eval} -> Aborted limit={k_path_limit}). "
            f"Para salvaguardar la inviolabilidad del codigo y prevenir una regresion silente, "
            f"procedo a subdividir la instruccion genesis en dos operaciones de encapsulamiento."
        )

        # Gap 5: Generate resumption token and store state for later resume
        resumption_token = uuid.uuid4().hex
        resumption_state = {
            "token": resumption_token,
            "subtasks": subtasks,
            "subtask_results": subtask_results or [],
            "original_intent": {
                "op": intent.op,
                "target": intent.target,
                "goal": intent.goal,
                "language": intent.language,
                "raw_code": intent.raw_code,
                "scrap_query": intent.scrap_query,
                "confidence": intent.confidence,
            },
            "partial_code": combined_code,
            "created_at": time.time(),
        }
        with orch._resumptions_lock:
            orch._pending_resumptions[resumption_token] = resumption_state

        # Clean up old resumptions: TTL-based (30 min) + count-based (keep last 100)
        _RESUMPTION_TTL_SECONDS = 30 * 60  # 30 minutes
        with orch._resumptions_lock:
            # Remove entries older than TTL
            now = time.time()
            expired_keys = [
                k for k, v in orch._pending_resumptions.items()
                if now - v.get("created_at", 0) > _RESUMPTION_TTL_SECONDS
            ]
            for k in expired_keys:
                del orch._pending_resumptions[k]

            # Also enforce max count
            if len(orch._pending_resumptions) > 100:
                oldest_keys = sorted(
                    orch._pending_resumptions.keys(),
                    key=lambda k: orch._pending_resumptions[k].get("created_at", 0)
                )
                for k in oldest_keys[:len(oldest_keys) - 100]:
                    del orch._pending_resumptions[k]

        return {
            "status": "PARTIAL_REASONING",
            "code": combined_code,
            "hash": "N/A",
            "error": trial.error_message,
            "processing_time_ms": elapsed,
            "route": routing.route,
            "criticality": routing.criticality,
            "solver_status": plan.solver_status,
            "ast_analysis": ast_analysis,
            "explanations": [content],
            "partial_reasoning": True,
            # OpenAI-compatible partial reasoning payload
            "partial_reasoning_payload": {
                "content": content,
                "tool_calls": [
                    {
                        "id": f"call_zenith_mcts_fragmentation_{uuid.uuid4().hex[:4]}",
                        "type": "function",
                        "function": {
                            "name": "zenith_mcts_plan",
                            "arguments": json.dumps({
                                "subtask_1_isolation": subtask_1,
                                "subtask_2_mutation": subtask_2,
                            })
                        }
                    }
                ],
                "finish_reason": "tool_calls",
            },
            # Gap 5: Resumption data for partial reasoning
            "resumption": {
                "token": resumption_token,
                "subtasks": subtasks,
                "original_intent": {
                    "op": intent.op,
                    "target": intent.target,
                    "goal": intent.goal,
                    "language": intent.language,
                },
                "partial_code": combined_code,
                "completed_subtasks": sum(
                    1 for r in (subtask_results or [])
                    if isinstance(r, dict) and r.get("status") in ("SUCCESS", "CACHED")
                ),
                "total_subtasks": len(subtask_results or []),
            },
            "usage_metadata": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                f"zenith_{solver_type.lower()}_compute_time_ms": plan.solver_proof.get("timeout_ms", 0) if plan.solver_proof else 0,
                "zenith_k_path_eval": k_path_eval,
                "structural_theorem_hash": "null_overload",
            },
            "warnings": trial.warnings,
            "paths_explored": trial.paths_explored,
            "paths_pruned": trial.paths_pruned,
        }
