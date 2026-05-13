"""
CABLE 1-4 methods + budget allocation mixin for ContextAgent.
"""

import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from ._imports import (
    logger, ContextEntry, ContextOutput,
    TOTAL_CONTEXT_BUDGET, DEFAULT_TOKEN_BUDGET,
    RECENCY_DECAY_FACTOR, OP_RELEVANCE_WEIGHTS,
    GOAL_RELEVANCE_WEIGHTS, MAX_ENTRIES_FOR_SCORING,
    MAX_PREFETCH_RESULTS,
)


class CablesMixin:
    """Mixin with CABLE 1-4 methods and budget allocation."""

    # ============================================================
    #  CABLE 1: Recopilar entradas de memoria
    # ============================================================

    def _collect_entries(self, message: str, op: str, goal: str) -> List[ContextEntry]:
        """Recopila entradas de todas las fuentes de memoria."""
        entries: List[ContextEntry] = []
        now = time.time()

        # Working Memory (contexto actual de la sesión)
        if self._smart_memory:
            try:
                for entry in self._smart_memory._working_memory[:MAX_ENTRIES_FOR_SCORING]:
                    age_seconds = now - entry.timestamp if entry.timestamp > 0 else 60
                    recency = RECENCY_DECAY_FACTOR ** (age_seconds / 60.0)

                    content = f"[{entry.operation}/{entry.goal}] Q:{entry.query[:60]}"
                    if entry.response:
                        content += f" A:{entry.response[:80]}"

                    entries.append(ContextEntry(
                        content=content,
                        source="working",
                        operation=entry.operation,
                        goal=entry.goal,
                        importance=entry.importance,
                        recency=recency,
                        token_estimate=len(content.split()),
                    ))
            except Exception as e:
                logger.debug(f"ContextAgent: Working memory collection failed: {e}")

        # Long-term Memory (soluciones previas relevantes)
        if self._smart_memory and self._semantic_engine and self._semantic_engine.is_loaded:
            try:
                similar = self._smart_memory.find_similar_solutions(message, top_k=5)
                for sol in similar:
                    content = f"[{sol.get('operation','')}/{sol.get('goal','')}] {sol.get('solution','')[:100]}"
                    entries.append(ContextEntry(
                        content=content,
                        source="long_term",
                        operation=sol.get("operation", ""),
                        goal=sol.get("goal", ""),
                        importance=sol.get("importance", 0.5),
                        recency=0.5,  # No tenemos timestamp, asumir mid
                        relevance_score=sol.get("similarity", 0.5),
                        token_estimate=len(content.split()),
                    ))
            except Exception as e:
                logger.debug(f"ContextAgent: Long-term memory collection failed: {e}")

        # Procedural Memory (patrones aprendidos relevantes)
        if self._smart_memory:
            try:
                patterns = self._smart_memory.find_patterns(
                    min_success_rate=0.6, limit=3
                )
                for pat in patterns:
                    content = f"[pattern/{pat.get('pattern_type','')}] {pat.get('description','')[:80]}"
                    entries.append(ContextEntry(
                        content=content,
                        source="procedural",
                        operation="",
                        goal="",
                        importance=pat.get("success_rate", 0.5),
                        recency=0.3,  # Patrones son más estables
                        token_estimate=len(content.split()),
                    ))
            except Exception as e:
                logger.debug(f"ContextAgent: Procedural memory collection failed: {e}")

        return entries[:MAX_ENTRIES_FOR_SCORING]

    # ============================================================
    #  CABLE 2: Scoring de relevancia
    # ============================================================

    def _score_entries(self, entries: List[ContextEntry],
                       current_op: str, current_goal: str) -> List[ContextEntry]:
        """
        Calcula score de relevancia para cada entrada.

        Score = w_importance * importance + w_recency * recency + w_relevance * relevance
        donde relevance = similitud de operation/goal con el intent actual.
        """
        w_importance = 0.3
        w_recency = 0.3
        w_relevance = 0.4

        # Obtener pesos de relevancia para la operation actual
        op_weights = OP_RELEVANCE_WEIGHTS.get(current_op, {})
        goal_weights = GOAL_RELEVANCE_WEIGHTS.get(current_goal, {})

        for entry in entries:
            # Relevancia por operation
            op_rel = op_weights.get(entry.operation, 0.1) if entry.operation else 0.1

            # Relevancia por goal
            goal_rel = goal_weights.get(entry.goal, 0.1) if entry.goal else 0.1

            # Combinar relevance (operation pesa más)
            relevance = 0.6 * op_rel + 0.4 * goal_rel

            # Si ya tenía score de similarity (long_term), combinar
            if entry.relevance_score > 0:
                relevance = 0.5 * relevance + 0.5 * entry.relevance_score

            # Score combinado
            entry.relevance_score = (
                w_importance * entry.importance +
                w_recency * entry.recency +
                w_relevance * relevance
            )

        # Ordenar por relevance score (descendente)
        entries.sort(key=lambda e: e.relevance_score, reverse=True)
        return entries

    # ============================================================
    #  CABLE 3: Compresión adaptativa
    # ============================================================

    def _compress_entries(self, entries: List[ContextEntry],
                          max_tokens: int, op: str, goal: str) -> Tuple[str, int]:
        """
        Comprime entradas al presupuesto de tokens.

        Estrategia (en orden de preferencia):
        1. Si hay LLM: Resumen semántico (manejado por prepare_context_with_runner)
        2. TF-IDF keyword extraction: Extraer terms más relevantes
        3. Raw truncation: Cortar por presupuesto

        Siempre devuelve texto comprimido dentro del presupuesto.
        """
        if not entries:
            return "", 0

        # Seleccionar entradas que caben en el presupuesto
        selected: List[ContextEntry] = []
        token_count = 0

        for entry in entries:
            if token_count + entry.token_estimate <= max_tokens:
                selected.append(entry)
                token_count += entry.token_estimate
            elif token_count + 30 <= max_tokens:
                # Truncar entrada parcialmente (mínimo 30 tokens)
                truncated = entry.content[:120]
                selected.append(ContextEntry(
                    content=truncated + "...",
                    source=entry.source,
                    relevance_score=entry.relevance_score,
                    token_estimate=30,
                ))
                token_count += 30
            # Si no cabe, skip

        if not selected:
            # Al menos incluir la entrada más relevante truncada
            best = entries[0]
            return best.content[:max_tokens * 4], 1

        # Construir contexto comprimido
        # Formato: "[op/goal:score] content | [op/goal:score] content | ..."
        parts = []
        for entry in selected:
            op_goal = f"{entry.operation}/{entry.goal}" if entry.operation else "ctx"
            score_str = f"{entry.relevance_score:.1f}"
            parts.append(f"[{op_goal}:{score_str}] {entry.content}")

        compressed = " | ".join(parts)

        # Safety: truncar si excede (por si los estimates fueron bajos)
        max_chars = max_tokens * 4
        if len(compressed) > max_chars:
            compressed = compressed[:max_chars - 3] + "..."

        return compressed, len(selected)

    # ============================================================
    #  CABLE 4: Pre-fetch de memorias relevantes
    # ============================================================

    def _prefetch_relevant(self, message: str, op: str,
                            goal: str) -> List[Dict[str, Any]]:
        """
        Pre-fetch memorias relevantes al intent actual.

        Carga proactivamente:
        - Soluciones previas para la misma operation
        - Episodios de errores similares (para DEBUG)
        - Patrones procedurales relevantes
        """
        results: List[Dict[str, Any]] = []

        if not self._smart_memory:
            return results

        # 1. Soluciones previas con misma operation
        try:
            if self._semantic_engine and self._semantic_engine.is_loaded:
                similar = self._smart_memory.find_similar_solutions(
                    message, top_k=3
                )
                for sol in similar[:2]:
                    results.append({
                        "type": "similar_solution",
                        "operation": sol.get("operation", ""),
                        "solution": sol.get("solution", "")[:150],
                        "similarity": sol.get("similarity", 0.0),
                    })
        except Exception as e:
            logger.debug(f"ContextAgent: Prefetch solutions failed: {e}")

        # 2. Episodios de errores (para DEBUG/BUG_FIX)
        if op in ("DEBUG",) or goal in ("BUG_FIX",):
            try:
                episodes = self._smart_memory.find_episodes(
                    event_type="error", limit=2
                )
                for ep in episodes[:2]:
                    results.append({
                        "type": "error_episode",
                        "description": ep.get("description", "")[:100],
                        "outcome": ep.get("outcome", ""),
                    })
            except Exception as e:
                logger.debug(f"ContextAgent: Prefetch episodes failed: {e}")

        # 3. Patrones procedurales (para CREATE/OPTIMIZE)
        if op in ("CREATE", "OPTIMIZE"):
            try:
                patterns = self._smart_memory.find_patterns(
                    min_success_rate=0.7, limit=2
                )
                for pat in patterns[:2]:
                    results.append({
                        "type": "procedural_pattern",
                        "name": pat.get("pattern_name", ""),
                        "success_rate": pat.get("success_rate", 0.0),
                        "steps": pat.get("steps", [])[:3],
                    })
            except Exception as e:
                logger.debug(f"ContextAgent: Prefetch patterns failed: {e}")

        return results[:MAX_PREFETCH_RESULTS]

    # ============================================================
    #  Presupuesto de Tokens
    # ============================================================

    def _allocate_budget(self, op: str, goal: str,
                          total: int = TOTAL_CONTEXT_BUDGET) -> Dict[str, int]:
        """
        Asigna presupuesto de tokens según operation/goal.

        Ajusta el presupuesto por defecto según la operación:
        - CREATE: más tokens para code (250), menos para validation (50)
        - DEBUG: más tokens para reasoning (200), menos para intent (30)
        - EXPLAIN: más tokens para reasoning (200), menos para code (100)
        """
        budget = DEFAULT_TOKEN_BUDGET.copy()

        # Ajustes por operation
        if op == "CREATE":
            budget["code"] = min(int(budget["code"] * 1.25), 280)
            budget["intent"] = max(int(budget["intent"] * 0.6), 30)
            budget["validation"] = max(int(budget["validation"] * 0.7), 50)
        elif op == "DEBUG":
            budget["reasoning"] = min(int(budget["reasoning"] * 1.33), 220)
            budget["intent"] = max(int(budget["intent"] * 0.6), 30)
            budget["code"] = max(int(budget["code"] * 0.75), 150)
        elif op == "EXPLAIN":
            budget["reasoning"] = min(int(budget["reasoning"] * 1.33), 220)
            budget["code"] = max(int(budget["code"] * 0.5), 100)
        elif op == "OPTIMIZE":
            budget["code"] = min(int(budget["code"] * 1.25), 280)
            budget["reasoning"] = max(int(budget["reasoning"] * 0.8), 120)
        elif op in ("ANALYZE", "SEARCH"):
            budget["reasoning"] = min(int(budget["reasoning"] * 1.2), 200)
            budget["code"] = max(int(budget["code"] * 0.7), 140)

        # Ajustes por goal (criticality)
        if goal == "SECURITY_HARDEN":
            budget["validation"] = min(int(budget["validation"] * 1.5), 180)
            budget["reserve"] = max(int(budget["reserve"] * 0.5), 50)
        elif goal == "BUG_FIX":
            budget["reasoning"] = min(int(budget["reasoning"] * 1.2), 200)
            budget["reserve"] = max(int(budget["reserve"] * 0.6), 60)
        elif goal == "PERFORMANCE":
            budget["code"] = min(int(budget["code"] * 1.15), 260)

        # Normalizar: asegurar que la suma no exceda el total
        total_allocated = sum(budget.values())
        if total_allocated > total:
            scale = total / total_allocated
            budget = {k: max(int(v * scale), 20) for k, v in budget.items()}

        return budget
