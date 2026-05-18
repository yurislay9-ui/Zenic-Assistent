//! Core types for the orchestrator module.
//!
//! Defines [`OrchestratorStatus`] and the [`Orchestrator`] struct itself.
//! All fields are `pub(crate)` so that `impl` blocks in sibling submodules
//! (`lifecycle`, `coordinator`) can access them.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};

use zenic_flow::WorkflowDefinition;
use zenic_graph::NodeCatalog;
use zenic_policy::PolicyEngine;
use zenic_proto::WorkflowId;
use zenic_runtime::{DagScheduler, FractalLoader, NodeExecutorRegistry};

use crate::config::OrchestratorConfig;
use crate::router::RequestRouter;
use crate::session::SessionStore;

// ---------------------------------------------------------------------------
// OrchestratorStatus
// ---------------------------------------------------------------------------

/// Current status of the orchestrator.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum OrchestratorStatus {
    /// The orchestrator has not been started yet.
    Initialized,
    /// The orchestrator is running and accepting requests.
    Running,
    /// The orchestrator has been shut down.
    Shutdown,
}

impl OrchestratorStatus {
    /// Whether the orchestrator is in a state that can accept requests.
    pub fn is_operational(self) -> bool {
        matches!(self, Self::Initialized | Self::Running)
    }
}

// ---------------------------------------------------------------------------
// Orchestrator
// ---------------------------------------------------------------------------

/// The main orchestrator for Zenic-Agents.
///
/// The orchestrator owns all subsystems and provides high-level methods
/// that coordinate between them. It is the single entry point for
/// external callers (FFI, CLI, HTTP API).
///
/// Subsystems owned by the orchestrator:
/// - [`NodeCatalog`] — node and subgraph descriptors
/// - [`NodeExecutorRegistry`] — node execution logic
/// - [`DagScheduler`] — DAG execution with memory management
/// - [`FractalLoader`] — on-demand subgraph loading
/// - [`PolicyEngine`] — access control with RBAC, rules, vetoes
/// - [`RequestRouter`] — request classification and routing
/// - [`SessionStore`] — active session management
pub struct Orchestrator {
    /// Configuration parameters.
    pub(crate) config: OrchestratorConfig,
    /// Current orchestrator status.
    pub(crate) status: OrchestratorStatus,
    /// Node catalog (descriptors for all nodes, super-nodes, subgraphs).
    /// E-09 FIX: Arc<RwLock<>> so the DagStepExecutor can share the same
    /// populated catalog instead of receiving an empty instance.
    pub(crate) catalog: Arc<RwLock<NodeCatalog>>,
    /// Node executor registry (maps NodeId → execution logic).
    /// E-09 FIX: Arc<RwLock<>> for sharing with DagStepExecutor.
    pub(crate) executors: Arc<RwLock<NodeExecutorRegistry>>,
    /// DAG scheduler (executes DAGs with memory awareness).
    /// E-09 FIX: Arc<RwLock<>> for sharing with DagStepExecutor.
    pub(crate) scheduler: Arc<RwLock<DagScheduler>>,
    /// Fractal loader (on-demand subgraph loading/unloading).
    #[allow(dead_code)]
    pub(crate) fractal_loader: FractalLoader,
    /// Policy engine (RBAC, rules, vetoes, audit).
    pub(crate) policy_engine: PolicyEngine,
    /// Request router (classifies incoming requests).
    pub(crate) router: RequestRouter,
    /// Session store (active sessions).
    pub(crate) sessions: SessionStore,
    /// Workflow definitions indexed by ID.
    pub(crate) workflow_definitions: HashMap<WorkflowId, WorkflowDefinition>,
    /// Monotonic clock for timestamps (milliseconds).
    pub(crate) clock_ms: u64,
}
