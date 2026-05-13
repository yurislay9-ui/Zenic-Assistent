"""
Core mixin for ContextAgent — BaseAgent interface, high-level API, and utilities.
"""

import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from ._imports import (
    logger, BaseAgent, AgentResult, IntentOutput,
    ContextEntry, ContextOutput,
    TOTAL_CONTEXT_BUDGET, DEFAULT_TOKEN_BUDGET,
)


class CoreMixin:
    """Mixin with BaseAgent interface methods, high-level API, and utilities."""

    # ============================================================
    #  BaseAgent INTERFACE
    # ============================================================

    def build_prompt(self, input_data: Any) -> Tuple[str, str]:
        """
        Construye prompt para compresión de contexto vía LLM.

        Input esperado: dict con keys:
          - raw_context: str (contexto sin comprimir)
          - intent_operation: str (operation actual)
          - intent_goal: str (goal actual)
          - max_tokens: int (presupuesto de tokens)
        """
        raw_ctx = input_data.get("raw_context", "") if isinstance(input_data, dict) else str(input_data)
        op = input_data.get("intent_operation", "SEARCH") if isinstance(input_data, dict) else "SEARCH"
        goal = input_data.get("intent_goal", "FEATURE_ADD") if isinstance(input_data, dict) else "FEATURE_ADD"
        max_t = input_data.get("max_tokens", 200) if isinstance(input_data, dict) else 200

        # Prompt ultra-compacto para Qwen3-0.6B
        system = (
            "Compress context for AI agent. Keep only essential info. "
            f"Max {max_t} tokens. Format: key:value pairs separated by |. "
            "Prioritize: errors, solutions, patterns relevant to "
            f"{op}/{goal}. Reply ONLY compressed text, no explanation."
        )
        user = f"Context to compress:\n{raw_ctx[:400]}"
        return system, user

    def parse_response(self, raw_response: str, input_data: Any) -> Optional[ContextOutput]:
        """Parsea respuesta comprimida del LLM."""
        cleaned = self.clean_llm_text(raw_response).strip()
        if not cleaned or len(cleaned) < 10:
            return None

        # La respuesta del LLM es el contexto comprimido directamente
        max_tokens = input_data.get("max_tokens", 200) if isinstance(input_data, dict) else 200
        raw_ctx = input_data.get("raw_context", "") if isinstance(input_data, dict) else str(input_data)

        # Estimar tokens (1 token ≈ 4 chars para inglés, ≈2 chars para español)
        compressed_tokens = len(cleaned.split())
        raw_tokens = len(raw_ctx.split()) if raw_ctx else 1

        return ContextOutput(
            compressed_context=cleaned[:max_tokens * 4],
            token_budget=DEFAULT_TOKEN_BUDGET.copy(),
            compression_ratio=min(compressed_tokens / max(raw_tokens, 1), 1.0),
            source="llm",
        )

    def fallback(self, input_data: Any) -> ContextOutput:
        """
        Fallback determinista: compresión sin LLM.

        Flujo: SmartMemory → Scoring → TF-IDF/Raw compression → Budget
        """
        start = time.time()

        # Extraer parámetros
        if isinstance(input_data, dict):
            message = input_data.get("message", "")
            intent_output = input_data.get("intent_output")
            max_tokens = input_data.get("max_tokens", TOTAL_CONTEXT_BUDGET)
        else:
            message = str(input_data)
            intent_output = None
            max_tokens = TOTAL_CONTEXT_BUDGET

        # Open Design: Apply Design System budget multiplier
        if getattr(self, '_design_system_mode', False):
            max_tokens = int(max_tokens * getattr(self, '_design_system_budget_multiplier', 1.0))

        # Obtener operation/goal para scoring
        op = intent_output.operation if intent_output else "SEARCH"
        goal = intent_output.goal if intent_output else "FEATURE_ADD"

        # CABLE 1: Recopilar entradas de memoria
        entries = self._collect_entries(message, op, goal)

        # CABLE 2: Scoring de relevancia
        scored_entries = self._score_entries(entries, op, goal)

        # CABLE 3: Compresión adaptativa (TF-IDF o raw)
        compressed, entries_used = self._compress_entries(
            scored_entries, max_tokens, op, goal
        )

        # CABLE 4: Pre-fetch de memorias relevantes
        relevant = self._prefetch_relevant(message, op, goal)

        # Calcular presupuesto de tokens
        budget = self._allocate_budget(op, goal, max_tokens)

        # Calcular métricas
        raw_tokens = sum(e.token_estimate for e in entries)
        comp_tokens = len(compressed.split()) if compressed else 0
        ratio = min(comp_tokens / max(raw_tokens, 1), 1.0) if raw_tokens > 0 else 1.0

        # Cache compartido — store with per-entry timestamp
        self._shared_context_cache[f"{op}:{goal}"] = (compressed, time.time())

        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("fallback", duration_ms)

        # Scores para logging
        scores = {f"{e.operation}/{e.goal}": round(e.relevance_score, 2)
                  for e in scored_entries[:5]}

        return ContextOutput(
            compressed_context=compressed,
            relevant_memories=relevant,
            token_budget=budget,
            context_scores=scores,
            entries_used=entries_used,
            entries_total=len(entries),
            compression_ratio=ratio,
            source="fallback",
            duration_ms=duration_ms,
        )

    # ============================================================
    #  HIGH-LEVEL API (lo que el DAG y agentes llaman)
    # ============================================================

    def prepare_context(self, message: str, intent_output: IntentOutput = None,
                        max_tokens: int = TOTAL_CONTEXT_BUDGET) -> ContextOutput:
        """
        Método principal: prepara contexto óptimo para el pipeline.

        Este es el método que el DAGOrchestrator llama en el nodo
        CONTEXT_PREPARE.
        """
        # Open Design: Expand context budget for Design Systems
        if getattr(self, '_design_system_mode', False):
            max_tokens = int(max_tokens * getattr(self, '_design_system_budget_multiplier', 1.0))

        input_data = {
            "message": message,
            "intent_output": intent_output,
            "max_tokens": max_tokens,
        }
        return self.fallback(input_data)

    def prepare_context_with_runner(self, runner: Any, message: str,
                                     intent_output: IntentOutput = None,
                                     max_tokens: int = TOTAL_CONTEXT_BUDGET) -> ContextOutput:
        """Prepara contexto usando AgentRunner (LLM → fallback)."""
        # Primero intentar fallback (siempre funciona, sin costo LLM)
        fallback_result = self.prepare_context(message, intent_output, max_tokens)

        # Si el contexto es pequeño o ya bien comprimido, no gastar LLM
        raw_token_est = len(message.split())
        if raw_token_est < 50 or not self._smart_memory:
            return fallback_result

        # Si hay contexto largo que comprimir, intentar LLM
        if runner and runner._mini_ai and runner._mini_ai.is_loaded:
            # Solo usar LLM si hay contexto significativo que comprimir
            working_ctx = self._get_raw_working_context()
            if len(working_ctx.split()) > 100:
                try:
                    llm_input = {
                        "raw_context": working_ctx[:600],
                        "intent_operation": intent_output.operation if intent_output else "SEARCH",
                        "intent_goal": intent_output.goal if intent_output else "FEATURE_ADD",
                        "max_tokens": max_tokens,
                    }
                    result: AgentResult = runner.run(self, llm_input)
                    if result.success and isinstance(result.data, ContextOutput):
                        # Enriquecer resultado LLM con pre-fetch y budget
                        result.data.relevant_memories = fallback_result.relevant_memories
                        result.data.token_budget = fallback_result.token_budget
                        result.data.entries_used = fallback_result.entries_used
                        result.data.entries_total = fallback_result.entries_total
                        return result.data
                except Exception as e:
                    logger.debug(f"ContextAgent: LLM compression failed: {e}")

        return fallback_result

    def get_context_for_agent(self, agent_name: str, intent_output: IntentOutput = None,
                               max_tokens: int = None) -> str:
        """
        Obtiene contexto comprimido para un agente específico.

        Aplica deduplicación: no envía contexto que ya se envió al mismo agente.
        Respeta el presupuesto de tokens del agente.
        """
        op = intent_output.operation if intent_output else "SEARCH"
        goal = intent_output.goal if intent_output else "FEATURE_ADD"

        # Buscar en cache compartido
        cache_key = f"{op}:{goal}"
        cached_entry = self._shared_context_cache.get(cache_key)
        cached = ""
        cache_age = float('inf')
        if cached_entry:
            cached, ts = cached_entry
            cache_age = time.time() - ts

        # Si el cache es muy viejo, invalidar
        if cache_age > self._shared_context_ttl or not cached:
            ctx = self.prepare_context(
                "", intent_output, max_tokens or TOTAL_CONTEXT_BUDGET
            )
            cached = ctx.compressed_context

        # Aplicar presupuesto de tokens del agente
        budget = DEFAULT_TOKEN_BUDGET.get(agent_name, 100)

        # Open Design: Expand budget for Design System preservation
        if getattr(self, '_design_system_mode', False):
            budget = int(budget * getattr(self, '_design_system_budget_multiplier', 1.0))

        if max_tokens:
            budget = min(budget, max_tokens)

        # Truncar al presupuesto (1 token ≈ 4 chars)
        max_chars = budget * 4
        context = cached[:max_chars]

        # Deduplicación: trackear qué ya se envió
        if agent_name not in self._agent_context_sent:
            self._agent_context_sent[agent_name] = set()

        content_hash = hash(context)
        if content_hash in self._agent_context_sent[agent_name]:
            # Ya se envió este contexto exacto — no repetir
            return ""
        self._agent_context_sent[agent_name].add(content_hash)

        return context

    def reset_agent_tracking(self) -> None:
        """Resetea tracking de deduplicación (al inicio de cada request)."""
        self._agent_context_sent.clear()

    def get_token_budget_for(self, agent_name: str) -> int:
        """Obtiene el presupuesto de tokens para un agente."""
        return DEFAULT_TOKEN_BUDGET.get(agent_name, 100)

    # ============================================================
    #  UTILIDADES
    # ============================================================

    def _get_raw_working_context(self) -> str:
        """Obtiene contexto raw de working memory para compresión LLM."""
        if not self._smart_memory:
            return ""
        try:
            return self._smart_memory.get_working_context(max_tokens=400)
        except Exception:
            return ""

    def get_compressed_working_context(self, intent_output: IntentOutput = None,
                                        max_tokens: int = 200) -> str:
        """
        Reemplazo directo para SmartMemory.get_working_context().

        Este método se puede usar como drop-in replacement:
        En vez de: ctx = self._memory.get_working_context(200)
        Usar:      ctx = self._context_agent.get_compressed_working_context(intent, 200)
        """
        op = intent_output.operation if intent_output else "SEARCH"
        goal = intent_output.goal if intent_output else "FEATURE_ADD"

        # Verificar cache compartido
        cache_key = f"{op}:{goal}"
        if cache_key in self._shared_context_cache:
            cached, ts = self._shared_context_cache[cache_key]
            cache_age = time.time() - ts
            if cache_age < self._shared_context_ttl:
                return cached[:max_tokens * 4]

        # Calcular fresh
        result = self.prepare_context("", intent_output, max_tokens)
        return result.compressed_context[:max_tokens * 4]

    @property
    def budget_stats(self) -> Dict[str, Any]:
        """Estadísticas de uso del presupuesto de tokens."""
        return {
            "default_budget": DEFAULT_TOKEN_BUDGET,
            "total_budget": TOTAL_CONTEXT_BUDGET,
            "shared_cache_entries": len(self._shared_context_cache),
            "shared_cache_age": "per-entry",
            "agents_tracked": list(self._agent_context_sent.keys()),
        }
