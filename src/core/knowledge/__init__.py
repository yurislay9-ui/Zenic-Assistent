from __future__ import annotations

try:
    from .types import KnowledgeNode, KnowledgeEdge, KnowledgeQuery, KnowledgeSearchResult, GraphDomain
except ImportError:
    KnowledgeNode = None  # type: ignore[misc,assignment]
    KnowledgeEdge = None  # type: ignore[misc,assignment]
    KnowledgeQuery = None  # type: ignore[misc,assignment]
    KnowledgeSearchResult = None  # type: ignore[misc,assignment]
    GraphDomain = None  # type: ignore[misc,assignment]

try:
    from .graph_engine import KnowledgeGraphEngine, get_knowledge_graph, reset_knowledge_graph
except ImportError:
    KnowledgeGraphEngine = None  # type: ignore[misc,assignment]
    get_knowledge_graph = None  # type: ignore[misc,assignment]
    reset_knowledge_graph = None  # type: ignore[misc,assignment]

try:
    from .cross_agent import CrossAgentKnowledgeBus, get_cross_agent_bus, reset_cross_agent_bus
except ImportError:
    CrossAgentKnowledgeBus = None  # type: ignore[misc,assignment]
    get_cross_agent_bus = None  # type: ignore[misc,assignment]
    reset_cross_agent_bus = None  # type: ignore[misc,assignment]

__all__ = [
    "KnowledgeNode",
    "KnowledgeEdge",
    "KnowledgeQuery",
    "KnowledgeSearchResult",
    "GraphDomain",
    "KnowledgeGraphEngine",
    "get_knowledge_graph",
    "reset_knowledge_graph",
    "CrossAgentKnowledgeBus",
    "get_cross_agent_bus",
    "reset_cross_agent_bus",
]
