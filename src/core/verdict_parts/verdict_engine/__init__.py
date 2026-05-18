"""VerdictEngine - AI only says YES or NO."""

import os
import re
import time
import logging
import concurrent.futures
from typing import Optional, Dict, Any, List

from ..types import (
    EvidenceType, Verdict, Evidence, VerdictInput, VerdictOutput,
    ConsensusResult, VerdictConfidence,
)
from ..evidence_collector import EvidenceCollector
from ..consensus_resolver import ConsensusResolver
from ..deterministic_pipeline import DeterministicPipeline

try:
    from ..resilience import (
        VerdictCircuitBreaker, VerdictRetryConfig, VerdictHealthMonitor,
        VerdictAuditor, VerdictAuditEntry, VerdictResilienceOrchestrator,
    )
    _RESILIENCE_AVAILABLE = True
except ImportError:
    _RESILIENCE_AVAILABLE = False

from ._config import VERDICT_TIMEOUT_S, VERDICT_MAX_TOKENS, VERDICT_TEMPERATURE, VERDICT_MAX_RETRIES, VERDICT_CONSENSUS_ATTEMPTS, VERDICT_CONSENSUS_THRESHOLD
from ._llm_mixin import VerdictLLMMixin
from ._helpers_mixin import VerdictHelpersMixin

logger = logging.getLogger("zenic_agents.verdict_parts.verdict_engine")

__all__ = ["VerdictEngine"]


class VerdictEngine(VerdictLLMMixin, VerdictHelpersMixin):
    """Motor de Veredicto: la IA solo dice SI o NO."""


    def __init__(self, mini_ai=None, semantic_engine=None,
                 smart_memory=None, auto_load: bool = True):
        """
        Args:
            mini_ai: Instancia de MiniAIEngine (Qwen3-0.6B) - OPCIONAL
            semantic_engine: Instancia de SemanticEngine - OPCIONAL
            smart_memory: Instancia de SmartMemory - OPCIONAL
            auto_load: Si True, carga el modelo al inicializar
        """
        self._mini_ai = mini_ai
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._memory_chip = None  # Injected from _zenic_native

        # Subsistemas determinísticos (siempre disponibles)
        self._pipeline = DeterministicPipeline()
        self._evidence_collector = EvidenceCollector()
        self._consensus_resolver = ConsensusResolver()

        # Stats
        self._total_verdicts = 0
        self._llm_verdicts = 0
        self._consensus_verdicts = 0
        self._low_confidence_verdicts = 0
        self._fallback_verdicts = 0
        self._yes_count = 0
        self._no_count = 0
        self._total_time = 0.0

        # Executor para timeout
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)

        # v17.1: Resilience orchestrator
        if _RESILIENCE_AVAILABLE:
            self._resilience = VerdictResilienceOrchestrator(
                circuit_breaker=VerdictCircuitBreaker(
                    name="verdict_engine",
                    failure_threshold=3,
                    recovery_timeout=60.0,
                    half_open_max_calls=1,
                    success_threshold=2,
                ),
                health_monitor=VerdictHealthMonitor(
                    window_size=50,
                    unhealthy_threshold=0.3,
                ),
                auditor=VerdictAuditor(max_entries=200),
                retry_config=VerdictRetryConfig(
                    max_attempts=VERDICT_MAX_RETRIES,
                    base_delay=1.0,
                    max_delay=10.0,
                    timeout_per_attempt=VERDICT_TIMEOUT_S,
                ),
            )
        else:
            self._resilience = None

    def set_memory_chip(self, chip) -> None:
        """Inject the Memory Chip reference (via PyO3 bridge)."""
        self._memory_chip = chip

    def shutdown(self):
        """Shut down the internal ThreadPoolExecutor to prevent resource leaks.

        Call this when the VerdictEngine is no longer needed (e.g. on server
        shutdown).  Without this the executor's worker thread keeps running.
        """
        executor = getattr(self, '_executor', None)
        if executor is not None:
            executor.shutdown(wait=False)
            self._executor = None

    def __del__(self):
        """Ensure executor is cleaned up on garbage collection."""
        try:
            self.shutdown()
        except Exception:
            pass

        # NOTE: Do NOT log here — __del__ runs during garbage collection and
        # referencing self._mini_ai / self._semantic may already be invalid.
        # The original code used bare names (mini_ai, semantic_engine) which
        # caused NameError at GC time.

    # ================================================================
    #  MAIN API: Full verdict pipeline
    # ================================================================

    def verdict(self, text: str, code: str = "",
                language: str = "python",
                question: str = "Should this code be approved?",
                context: Optional[Dict[str, Any]] = None) -> VerdictOutput:
        """
        Ejecuta el pipeline completo de veredicto con resiliencia.

        Este es el punto de entrada principal. Recorre:
          1. DeterministicPipeline (tareas sin IA)
          2. EvidenceCollector (evidencia sin IA)
          3. ConsensusResolver (consenso sin IA)
          4. Si hay empate → Circuit Breaker check → LLM arbitraje
          5. Multi-attempt consensus para mayor confiabilidad
          6. Audit del resultado
        """
        start_time = time.time()
        self._total_verdicts += 1
        ctx = context or {}

        # === MEMORY CHIP PRE-CHECK (T2-17, T1-15) ===
        # If the memory chip has a high-confidence mapping, bypass the entire
        # verdict pipeline and return immediately. This is the <5ms path.
        if self._memory_chip is None:
            logger.debug("Memory chip not initialized — PyO3 module may not be loaded")
        if self._memory_chip is not None:
            try:
                chip_result = self._memory_chip.lookup(text, ctx.get("tenant_id", "__anonymous__"))
                if chip_result and chip_result.get("cache_hit"):
                    # SECURITY (C1 fix): Before returning YES from cache,
                    # check for veto-level evidence against. If any exists,
                    # fall through to the normal pipeline instead.
                    veto_evidence = self._evidence_collector.collect_all_evidence(
                        text, code, language,
                        memory_chip=self._memory_chip,
                        tenant_id=ctx.get("tenant_id", "__anonymous__"),
                    )
                    has_veto = any(
                        e.favors == Verdict.NO
                        and e.evidence_type in (EvidenceType.SECURITY_CHECK, EvidenceType.SANDBOX_PASS)
                        and e.weight >= 0.7
                        for e in veto_evidence
                    )
                    if has_veto:
                        logger.warning(
                            "Memory chip cache hit for '%s' overridden by veto evidence — "
                            "falling through to full pipeline", text[:80]
                        )
                        # Fall through to normal pipeline below
                    else:
                        mapping = chip_result.get("mapping", {})
                        confidence = 0.9  # Memory chip mappings are pre-approved
                        # NOTE: A4 fix — removed duplicate self._total_verdicts increment;
                        # the counter was already bumped at the top of verdict()
                        self._consensus_verdicts += 1
                        self._yes_count += 1
                        return VerdictOutput(
                            verdict=Verdict.YES,
                            confidence=confidence,
                            source="memory_chip_cache",
                            evidence_summary=f"Memory chip cache hit: '{text}' → '{mapping.get('destination', '?')}' "
                                             f"(mechanism: {mapping.get('mechanism', 'unknown')})",
                            llm_used=False,
                            llm_raw_response="",
                            retry_count=0,
                        )
            except Exception as exc:
                logger.debug("Memory chip pre-check error: %s", exc)

        # === PASO 1: Ejecutar pipeline determinístico ===
        pipeline_results = self._pipeline.execute_all(text, code, language, ctx)

        # === PASO 2: Recolectar evidencia ===
        evidence = self._evidence_collector.collect_all_evidence(
            text, code, language,
            memory_chip=self._memory_chip,
            tenant_id=ctx.get("tenant_id", "__anonymous__"),
        )

        # Agregar evidencia de los resultados del pipeline
        for task_name, result in pipeline_results.items():
            if result.confidence >= 0.8:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.RULE_ENGINE,
                    favors=Verdict.YES,
                    weight=result.confidence,
                    source=f"pipeline_{task_name}",
                    detail=f"Pipeline task {task_name} succeeded with confidence {result.confidence:.2f}",
                ))

        # === PASO 3: Resolver consenso ===
        consensus = self._consensus_resolver.resolve(evidence, question)

        # === PASO 4: Decidir si necesita IA ===
        if not consensus.needs_llm:
            # Consenso claro: no necesita IA
            elapsed = time.time() - start_time
            self._total_time += elapsed

            if consensus.confidence in (VerdictConfidence.CERTAIN, VerdictConfidence.HIGH):
                self._consensus_verdicts += 1
            else:
                self._low_confidence_verdicts += 1

            if consensus.verdict == Verdict.YES:
                self._yes_count += 1
            else:
                self._no_count += 1

            # Build evidence summary
            evidence_summary = self._build_evidence_summary(consensus)

            # Audit consensus verdict
            self._audit_result(
                question, consensus.verdict.value, "consensus",
                False, abs(consensus.score), int(elapsed * 1000), 0,
                len(consensus.evidence_for), len(consensus.evidence_against),
                consensus.score
            )

            return VerdictOutput(
                verdict=consensus.verdict,
                confidence=abs(consensus.score),
                source="consensus",
                evidence_summary=evidence_summary,
                llm_used=False,
                llm_raw_response="",
                retry_count=0,
            )

        # === PASO 5: Arbitraje de IA con resiliencia ===
        if self._resilience is None:
            logger.debug("Resilience orchestrator not available — running without circuit breaker")
        verdict_input = VerdictInput(
            question=question,
            evidence_for=consensus.evidence_for,
            evidence_against=consensus.evidence_against,
            consensus_score=consensus.score,
            context=self._build_context_summary(text, code, pipeline_results),
        )

        return self._request_llm_verdict(verdict_input, start_time)

    # ================================================================
    #  DIRECT API: Ask LLM directly (only YES/NO)
    # ================================================================

    def ask_yes_no(self, question: str,
                   context: str = "",
                   evidence_for: Optional[List[Evidence]] = None,
                   evidence_against: Optional[List[Evidence]] = None) -> VerdictOutput:
        """
        Pregunta directamente a la IA una pregunta de SÍ o NO.

        v17.1: Ahora con circuit breaker, retry, y consensus.
        """
        start_time = time.time()
        self._total_verdicts += 1

        verdict_input = VerdictInput(
            question=question,
            evidence_for=evidence_for or [],
            evidence_against=evidence_against or [],
            consensus_score=0.0,
            context=context,
        )

        return self._request_llm_verdict(verdict_input, start_time)

    # ================================================================
    #  STATS
    # ================================================================

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadísticas del VerdictEngine con resiliencia."""
        total = max(self._total_verdicts, 1)
        base_stats = {
            "total_verdicts": self._total_verdicts,
            "llm_verdicts": self._llm_verdicts,
            "consensus_verdicts": self._consensus_verdicts,
            "low_confidence_verdicts": self._low_confidence_verdicts,
            "fallback_verdicts": self._fallback_verdicts,
            "yes_count": self._yes_count,
            "no_count": self._no_count,
            "llm_rate": self._llm_verdicts / total,
            "consensus_rate": self._consensus_verdicts / total,
            "low_confidence_rate": self._low_confidence_verdicts / total,
            "fallback_rate": self._fallback_verdicts / total,
            "yes_rate": self._yes_count / total,
            "no_rate": self._no_count / total,
            "avg_time_s": self._total_time / total,
            "llm_available": self._mini_ai is not None and self._mini_ai.is_loaded,
            "consensus_attempts": VERDICT_CONSENSUS_ATTEMPTS,
            "max_retries": VERDICT_MAX_RETRIES,
        }
        if self._resilience:
            base_stats["resilience"] = self._resilience.stats
        return base_stats

    @property
    def health(self) -> Dict[str, Any]:
        """Health status of the verdict system."""
        if self._resilience:
            snap = self._resilience.health_snapshot
            return {
                "is_healthy": snap.is_healthy,
                "success_rate": snap.success_rate,
                "avg_latency_s": snap.avg_latency_s,
                "circuit_breaker_state": snap.circuit_breaker_state,
            }
        return {
            "is_healthy": self._mini_ai is not None and self._mini_ai.is_loaded,
            "success_rate": "unknown",
            "avg_latency_s": "unknown",
            "circuit_breaker_state": "not_configured",
        }

    # ================================================================
    #  LIFECYCLE
    # ================================================================

    def update_engines(self, mini_ai=None, semantic_engine=None,
                       smart_memory=None, memory_chip=None) -> None:
        """Actualiza las referencias a los motores."""
        if mini_ai is not None:
            self._mini_ai = mini_ai
        if semantic_engine is not None:
            self._semantic = semantic_engine
        if smart_memory is not None:
            self._memory = smart_memory
        if memory_chip is not None:
            self._memory_chip = memory_chip
            # Also inject into the pipeline
            self._pipeline.set_memory_chip(memory_chip)

        logger.info(
            f"VerdictEngine: Updated engines - "
            f"LLM={'available' if self._mini_ai and self._mini_ai.is_loaded else 'not available'}"
        )

    def reset_circuit_breaker(self) -> None:
        """Reset the circuit breaker to CLOSED state."""
        if self._resilience:
            self._resilience.circuit_breaker.reset()
            logger.info("VerdictEngine: Circuit breaker reset to CLOSED")

    def get_audit_trail(self, count: int = 20) -> List[Dict[str, Any]]:
        """Get recent audit entries as dictionaries."""
        if self._resilience and _RESILIENCE_AVAILABLE:
            entries = self._resilience.auditor.get_recent(count)
            return [
                {
                    "timestamp": e.timestamp,
                    "question": e.question,
                    "verdict": e.verdict,
                    "source": e.source,
                    "llm_used": e.llm_used,
                    "confidence": e.confidence,
                    "latency_ms": e.latency_ms,
                    "circuit_breaker_state": e.circuit_breaker_state,
                }
                for e in entries
            ]
        return []

    def get_failure_pattern(self) -> Dict[str, Any]:
        """Analyze recent verdicts for failure patterns."""
        if self._resilience:
            return self._resilience.auditor.get_failure_pattern()
        return {"pattern": "no_data", "risk": "unknown"}
