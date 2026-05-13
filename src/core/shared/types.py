"""
ZENIC-AGENTS - Data Types & Payloads v16

Operation types, goal types, criticality levels, route paths,
and data payloads for communication between pipeline levels.
"""

import enum
from typing import Any, Dict, List, Optional, Union

__all__ = [
    "OperationType", "GoalType", "CriticalityLevel", "RoutePath",
    "IntentPayload", "RoutingPayload", "PlanStep", "ExecutionPlan",
    "SandboxResult", "MerkleNode", "ChatMessage", "ChatRequest",
    "criticality_to_int", "criticality_to_path", "criticality_to_str",
    "CRITICALITY_INT_TO_STR", "CRITICALITY_STR_TO_INT",
    "CRITICALITY_INT_TO_PATH", "CRITICALITY_PATH_TO_INT",
]


# ============================================================
#  OPERACIONES Y OBJETIVOS
# ============================================================

class OperationType(str, enum.Enum):
    CREATE = "CREATE"
    REFACTOR = "REFACTOR"
    DELETE = "DELETE"
    SEARCH = "SEARCH"
    ANALYZE = "ANALYZE"
    EXPLAIN = "EXPLAIN"
    DEBUG = "DEBUG"
    OPTIMIZE = "OPTIMIZE"


class GoalType(str, enum.Enum):
    COMPLEXITY_REDUCTION = "COMPLEXITY_REDUCTION"
    MODERN_PATTERN = "MODERN_PATTERN"
    BUG_FIX = "BUG_FIX"
    FEATURE_ADD = "FEATURE_ADD"
    SECURITY_HARDEN = "SECURITY_HARDEN"
    PERFORMANCE = "PERFORMANCE"
    READABILITY = "READABILITY"
    AUTOMATION = "AUTOMATION"


class CriticalityLevel(int, enum.Enum):
    FAST_STANDARD = 1
    DEEP_MODERATE = 2
    SURGICAL_CRITICAL = 3


# ============================================================
#  CRITICALITY CONVERSION UTILS (single source of truth)
#  Resolves the 4-format criticality inconsistency:
#    int (1/2/3), str ("standard"/"moderate"/"critical"),
#    str ("low_crit"/"standard"/"high_crit"), CriticalityLevel constants
# ============================================================

CRITICALITY_INT_TO_STR = {
    1: "standard",
    2: "moderate",
    3: "critical",
}

CRITICALITY_STR_TO_INT = {v: k for k, v in CRITICALITY_INT_TO_STR.items()}

CRITICALITY_INT_TO_PATH = {
    1: "low_crit",
    2: "standard",
    3: "high_crit",
}

CRITICALITY_PATH_TO_INT = {v: k for k, v in CRITICALITY_INT_TO_PATH.items()}


def criticality_to_int(value) -> int:
    """Convert any criticality representation to int (1/2/3)."""
    if isinstance(value, int):
        return max(1, min(3, value))
    if isinstance(value, str):
        if value in CRITICALITY_STR_TO_INT:
            return CRITICALITY_STR_TO_INT[value]
        if value in CRITICALITY_PATH_TO_INT:
            return CRITICALITY_PATH_TO_INT[value]
    return 2  # Default to DEEP_MODERATE


def criticality_to_path(value) -> str:
    """Convert any criticality representation to DAG path string."""
    return CRITICALITY_INT_TO_PATH.get(criticality_to_int(value), "standard")


def criticality_to_str(value) -> str:
    """Convert any criticality representation to human-readable string."""
    return CRITICALITY_INT_TO_STR.get(criticality_to_int(value), "moderate")


class RoutePath(str, enum.Enum):
    FAST_PATH = "FAST_PATH_REGEX"
    DEEP_PATH = "DEEP_PATH_CONSTRAINT"
    SURGICAL_PATH = "SURGICAL_PATH_FULL"


# ============================================================
#  PAYLOADS DE COMUNICACION ENTRE NIVELES
# ============================================================

class IntentPayload:
    def __init__(self, op: Union[str, OperationType] = OperationType.SEARCH.value, target: str = "unknown",
                 goal: Union[str, GoalType] = GoalType.FEATURE_ADD.value, scrap_query: str = "", confidence: float = 0.0,
                 language: str = "python", raw_code: str = "", context: str = "") -> None:
        self.op = op.value if isinstance(op, enum.Enum) else op
        self.target = target
        self.goal = goal.value if isinstance(goal, enum.Enum) else goal
        self.scrap_query = scrap_query
        self.confidence = confidence
        self.language = language
        self.raw_code = raw_code
        self.context = context


class RoutingPayload:
    def __init__(self, intent: Optional[IntentPayload] = None, criticality: Union[int, CriticalityLevel] = CriticalityLevel.FAST_STANDARD.value,
                 route: Union[str, RoutePath] = RoutePath.FAST_PATH.value, reason: str = "") -> None:
        self.intent = intent or IntentPayload()
        self.criticality = criticality.value if isinstance(criticality, enum.Enum) else criticality
        self.route = route.value if isinstance(route, enum.Enum) else route
        self.reason = reason


class PlanStep:
    def __init__(self, step_id: int = 0, action: str = "ANALYZE_CODE", target_node_name: str = "",
                 source: str = "LOCAL_GRAPH", constraints: Optional[Dict[str, Any]] = None) -> None:
        self.step_id = step_id
        self.action = action
        self.target_node_name = target_node_name
        self.source = source
        self.constraints = constraints or {}


class ExecutionPlan:
    def __init__(self, plan_id: str = "", steps: Optional[List[PlanStep]] = None, solver_status: str = "HEURISTIC_FALLBACK",
                 solver_proof: Optional[Any] = None, mcts_simulations: int = 0, mcts_depth_reached: int = 0) -> None:
        self.plan_id = plan_id
        self.steps = steps or []
        self.solver_status = solver_status
        self.solver_proof = solver_proof  # Resultado real del solver (Z3 o AC-3)
        self.mcts_simulations = mcts_simulations
        self.mcts_depth_reached = mcts_depth_reached


class SandboxResult:
    def __init__(self, status: str = "PASS", error_message: str = "", error_node: Optional[str] = None,
                 warnings: Optional[List[str]] = None, metrics: Optional[Dict[str, Any]] = None,
                 paths_explored: int = 0, paths_pruned: int = 0) -> None:
        self.status = status
        self.error_message = error_message
        self.error_node = error_node
        self.warnings = warnings or []
        self.metrics = metrics or {}
        self.paths_explored = paths_explored
        self.paths_pruned = paths_pruned


class MerkleNode:
    def __init__(self, file_path: str = "", hash_sha256: str = "", parent_hash: str = "",
                 timestamp: int = 0, operation: str = "") -> None:
        self.file_path = file_path
        self.hash_sha256 = hash_sha256
        self.parent_hash = parent_hash
        self.timestamp = timestamp
        self.operation = operation


class ChatMessage:
    def __init__(self, role: str = "user", content: str = "") -> None:
        self.role = role
        self.content = content


class ChatRequest:
    def __init__(self, model: str = "zenic-agents", messages: Optional[List[ChatMessage]] = None, temperature: float = 0.1,
                 max_tokens: int = 2000, stream: bool = False) -> None:
        self.model = model
        self.messages = messages or []
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.stream = stream
