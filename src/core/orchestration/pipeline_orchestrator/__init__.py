"""
Zenic-Agents Pipeline Orchestrator Package.

Core orchestration components for building, executing, and monitoring
pipeline DAGs with rollback support, compliance verification, and
event-driven communication.

Components:
    DAGBuilder — DAG construction and validation
    StepExecutor — Step execution engine
    RollbackManager — Rollback/recovery management
    StateTracker — Pipeline state tracking
    EventBus — Event pub/sub system
    DependencyResolver — Dependency resolution between steps
    PriorityQueue — Priority-based step queue
    ProgressMonitor — Pipeline progress monitoring
    ComplianceChecker — Compliance verification (HIPAA, PCI-DSS, etc.)
"""

from __future__ import annotations

from .dag_builder import DAGBuilder, DAGNode, DAGEdge, DAGValidationResult
from .step_executor import StepExecutor, StepResult, StepStatus
from .rollback_manager import RollbackManager, RollbackAction, RollbackResult
from .state_tracker import StateTracker, PipelineState, StepState
from .event_bus import EventBus, PipelineEvent, PipelineEventHandler
from .dependency_resolver import DependencyResolver, ResolutionResult, CircularDependencyError
from .priority_queue import PriorityQueue, PrioritizedItem
from .progress_monitor import ProgressMonitor, ProgressSnapshot, ProgressStatus
from .compliance_checker import ComplianceChecker, ComplianceResult, ComplianceStandard

__all__ = [
    "DAGBuilder",
    "DAGNode",
    "DAGEdge",
    "DAGValidationResult",
    "StepExecutor",
    "StepResult",
    "StepStatus",
    "RollbackManager",
    "RollbackAction",
    "RollbackResult",
    "StateTracker",
    "PipelineState",
    "StepState",
    "EventBus",
    "PipelineEvent",
    "PipelineEventHandler",
    "DependencyResolver",
    "ResolutionResult",
    "CircularDependencyError",
    "PriorityQueue",
    "PrioritizedItem",
    "ProgressMonitor",
    "ProgressSnapshot",
    "ProgressStatus",
    "ComplianceChecker",
    "ComplianceResult",
    "ComplianceStandard",
]
