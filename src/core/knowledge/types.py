from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional, Set


class GraphDomain(str, Enum):
    BUSINESS = "business"
    TECHNICAL = "technical"
    OPERATIONAL = "operational"
    SECURITY = "security"
    FINANCIAL = "financial"
    COMPLIANCE = "compliance"


@dataclass
class KnowledgeNode:
    id: str = ""
    domain: str = ""
    concept: str = ""
    content: str = ""
    tags: Set[str] = field(default_factory=set)
    confidence: float = 0.5
    source: str = ""
    created_at: str = ""
    updated_at: str = ""
    access_count: int = 0
    embedding_hash: str = ""


@dataclass
class KnowledgeEdge:
    id: str = ""
    source_id: str = ""
    target_id: str = ""
    relation_type: str = ""
    weight: float = 1.0
    created_at: str = ""


@dataclass
class KnowledgeQuery:
    domain: Optional[str] = None
    concept: Optional[str] = None
    tags: Set[str] = field(default_factory=set)
    min_confidence: float = 0.0
    max_results: int = 50
    semantic: bool = False


@dataclass
class KnowledgeSearchResult:
    nodes: List[KnowledgeNode] = field(default_factory=list)
    edges: List[KnowledgeEdge] = field(default_factory=list)
    total_matches: int = 0
    query_time_ms: float = 0.0
