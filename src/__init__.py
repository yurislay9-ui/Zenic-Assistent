"""
Zenic-Agents - Plataforma de Asistencia Empresarial Inteligente

Pipeline de 8 niveles con DAG Core (59 nodos), VerdictEngine AI,
9 Executors, SNA (Sistema Nervioso Autonomo), Blueprints Certificados,
Multi-Rol Colaborativo, Defense in Depth (6 capas) y Capa Conversacional.

Compatible con Android (Termux + proot-distro).
"""

__all__ = []  # Lazy-loaded via __getattr__


def __getattr__(name):
    if name == "ZenicAgents":
        from src.core.orchestrator import ZenicOrchestrator
        return ZenicOrchestrator
    if name == "ZenicOrchestrator":
        from src.core.orchestrator import ZenicOrchestrator
        return ZenicOrchestrator
    if name == "DAGOrchestrator":
        from zenic_core import Orchestrator as DAGOrchestrator  # type: ignore[import-unresolved]  # Migrated to zenic-core (Rust)
        return DAGOrchestrator
    if name == "patterns":
        from src.core import patterns
        return patterns
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
