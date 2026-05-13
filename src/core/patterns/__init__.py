"""
ZENIC-AGENTS - Design Patterns Package

Comprehensive design pattern library for the Zenic-Agents AI code
generation system, optimized for resource-constrained devices
(Android/Termux, 500MB RAM).

All patterns use only Python stdlib — no external dependencies.
All pattern classes are thread-safe.

Organization:

  Creational Patterns
  -------------------
    AgentFactory        — Thread-safe factory for BaseAgent instances
    FactoryRegistry     — Generic named-creator registry
    OrchestratorBuilder — Fluent builder for orchestrator config dicts
    AgentPrototype      — Deep-copy prototype for agent cloning

  Structural Patterns
  -------------------
    LLMAdapter          — ABC for LLM backend adapters
    LocalLLMAdapter     — Wraps MiniAIEngine._call_llm
    OpenAICompatibleAdapter — HTTP-based OpenAI API adapter
    FallbackLLMAdapter  — Primary → fallback chain
    AdapterRegistry     — Named LLMAdapter registry
    LLMProvider         — ABC for LLM providers (complete + embed)
    LocalProvider       — Local llama-cpp-python provider
    RemoteProvider      — HTTP API provider
    AgentLLMBridge      — Bridge with hot-swappable provider
    LazyProxy           — Deferred object creation proxy
    CacheProxy          — TTL-based method result cache proxy
    agent_decorator     — Capability-based method decorator factory
    AgentCapability     — Enum of decorator capabilities
    AgentDecorator      — Composable multi-capability decorator

  Behavioral Patterns
  -------------------
    StateMachine        — Thread-safe finite state machine
    State               — State dataclass with entry/exit callbacks
    Transition          — Transition dataclass with guard & action
    StrategyRegistry    — Named strategy registry with defaults
    ASTNode             — ABC for visitable AST nodes
    ASTVisitor          — ABC with double dispatch
    TokenCountVisitor   — Counts AST tokens per node type
    ComplexityVisitor   — Calculates cyclomatic complexity
    RefactorVisitor     — Marks nodes for refactoring
    VisitableAST        — Adapter making ast.AST nodes visitable

  Concurrency Patterns
  --------------------
    WorkerPool          — Dynamic, priority-aware thread pool
    WorkerPoolConfig    — Configuration dataclass for WorkerPool
    ProducerConsumer    — Bounded-buffer producer-consumer
    ReadWriteLock       — RW lock with writer preference (sync + async)

  Resilience Patterns
  -------------------
    CircuitBreaker      — Thread-safe circuit breaker with state machine
    CircuitState        — Enum for CLOSED/OPEN/HALF_OPEN states
    CircuitOpenError    — Exception when circuit is open
    RetryConfig         — Retry configuration dataclass
    retry               — Synchronous retry decorator
    retry_async         — Async retry decorator
    with_retry          — Synchronous retry context manager
    with_retry_async    — Async retry context manager
    RetryScope          — Scoped retry with counting
    Bulkhead            — Concurrency-limited execution with back-pressure
    BulkheadFullError   — Exception when bulkhead is full
    Sidecar             — Cross-cutting concern sidecar pattern
    sidecar_decorator   — Decorator for sidecar actions

  Orchestration Patterns
  ----------------------
    EventBus            — Observer/Pub-Sub for decoupled events
    Event               — Event dataclass
    EventHandler        — ABC for event handlers
    Mediator            — Centralized request/response dispatcher
    Request             — Request dataclass for mediator
    Response            — Response dataclass for mediator
    RequestHandler      — ABC for request handlers
    CommandBus          — Formal Command pattern dispatch
    OrchCommand         — Command dataclass for CommandBus
    OrchCommandHandler  — ABC for command handlers
    CommandResult       — Result dataclass for CommandBus
    Saga                — Multi-step rollback pattern
    SagaStep            — Saga step dataclass
    SagaContext         — Saga execution context
    SagaStatus          — Enum for saga states

  Architectural Patterns
  ----------------------
    CQRSBus             — Command/Query bus with validation & caching
    CQRSCommand         — Write operation dataclass
    Query               — Read operation dataclass
    CQRSCommandHandler  — ABC for command handlers
    QueryHandler        — ABC for query handlers
"""

# ---------------------------------------------------------------------------
# Creational
# ---------------------------------------------------------------------------
from src.core.patterns.creational import (
    AgentFactory,
    FactoryRegistry,
    OrchestratorBuilder,
    AgentPrototype,
)

# ---------------------------------------------------------------------------
# Structural
# ---------------------------------------------------------------------------
from src.core.patterns.structural import (
    LLMAdapter,
    LocalLLMAdapter,
    OpenAICompatibleAdapter,
    FallbackLLMAdapter,
    AdapterRegistry,
    LLMProvider,
    LocalProvider,
    RemoteProvider,
    AgentLLMBridge,
    LazyProxy,
    CacheProxy,
    agent_decorator,
    AgentCapability,
    AgentDecorator,
)

# ---------------------------------------------------------------------------
# Behavioral
# ---------------------------------------------------------------------------
from src.core.patterns.behavioral import (
    StateMachine,
    State,
    Transition,
    StrategyRegistry,
    ASTNode,
    ASTVisitor,
    TokenCountVisitor,
    ComplexityVisitor,
    RefactorVisitor,
    VisitableAST,
)

# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------
from src.core.patterns.concurrency import (
    WorkerPool,
    WorkerPoolConfig,
    ProducerConsumer,
    ReadWriteLock,
)

# ---------------------------------------------------------------------------
# Architectural (rename to avoid clash with orchestration Command)
# ---------------------------------------------------------------------------
from src.core.patterns.architectural import (
    CQRSBus,
    Command as CQRSCommand,
    Query,
    CommandHandler as CQRSCommandHandler,
    QueryHandler,
)

# ---------------------------------------------------------------------------
# Resilience
# ---------------------------------------------------------------------------
from src.core.patterns.resilience import (
    CircuitBreaker,
    CircuitState,
    CircuitOpenError,
    RetryConfig,
    retry,
    retry_async,
    with_retry,
    with_retry_async,
    RetryScope,
    Bulkhead,
    BulkheadFullError,
    Sidecar,
    sidecar_decorator,
)

# ---------------------------------------------------------------------------
# Orchestration (rename Command/CommandHandler to avoid clash with CQRS)
# ---------------------------------------------------------------------------
from src.core.patterns.orchestration import (
    EventBus,
    Event,
    EventHandler,
    Mediator,
    Request,
    Response,
    RequestHandler,
    CommandBus,
    Command as OrchCommand,
    CommandHandler as OrchCommandHandler,
    CommandResult,
    Saga,
    SagaStep,
    SagaContext,
    SagaStatus,
)

__all__ = [
    # Creational
    "AgentFactory",
    "FactoryRegistry",
    "OrchestratorBuilder",
    "AgentPrototype",
    # Structural
    "LLMAdapter",
    "LocalLLMAdapter",
    "OpenAICompatibleAdapter",
    "FallbackLLMAdapter",
    "AdapterRegistry",
    "LLMProvider",
    "LocalProvider",
    "RemoteProvider",
    "AgentLLMBridge",
    "LazyProxy",
    "CacheProxy",
    "agent_decorator",
    "AgentCapability",
    "AgentDecorator",
    # Behavioral
    "StateMachine",
    "State",
    "Transition",
    "StrategyRegistry",
    "ASTNode",
    "ASTVisitor",
    "TokenCountVisitor",
    "ComplexityVisitor",
    "RefactorVisitor",
    "VisitableAST",
    # Concurrency
    "WorkerPool",
    "WorkerPoolConfig",
    "ProducerConsumer",
    "ReadWriteLock",
    # Architectural
    "CQRSBus",
    "CQRSCommand",
    "Query",
    "CQRSCommandHandler",
    "QueryHandler",
    # Resilience
    "CircuitBreaker",
    "CircuitState",
    "CircuitOpenError",
    "RetryConfig",
    "retry",
    "retry_async",
    "with_retry",
    "with_retry_async",
    "RetryScope",
    "Bulkhead",
    "BulkheadFullError",
    "Sidecar",
    "sidecar_decorator",
    # Orchestration
    "EventBus",
    "Event",
    "EventHandler",
    "Mediator",
    "Request",
    "Response",
    "RequestHandler",
    "CommandBus",
    "OrchCommand",
    "OrchCommandHandler",
    "CommandResult",
    "Saga",
    "SagaStep",
    "SagaContext",
    "SagaStatus",
]
