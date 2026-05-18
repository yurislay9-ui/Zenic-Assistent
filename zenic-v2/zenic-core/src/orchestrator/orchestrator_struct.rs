//! Orchestrator struct definition and construction.

use std::collections::HashMap;
use std::sync::{Arc, RwLock};

use zenic_flow::WorkflowDefinition;
use zenic_graph::{NodeCatalog, NodeDescriptor, SubGraphDescriptor, SuperNodeDescriptor};
use zenic_policy::{PolicyEngine};
use zenic_proto::{NodeId, SessionId, TenantId, WorkflowId};
use zenic_runtime::{
    DagScheduler, FractalLoader, MemoryManager, NodeExecutor, NodeExecutorRegistry,
};

use crate::config::OrchestratorConfig;
use crate::errors::CoreError;
use crate::router::RequestRouter;
use crate::session::SessionStore;

use super::types::OrchestratorStatus;

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
    pub(crate) catalog: Arc<RwLock<NodeCatalog>>,
    /// Node executor registry (maps NodeId → execution logic).
    pub(crate) executors: Arc<RwLock<NodeExecutorRegistry>>,
    /// DAG scheduler (executes DAGs with memory awareness).
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

impl Orchestrator {
    /// Creates a new orchestrator with the given configuration.
    pub fn new(config: OrchestratorConfig) -> Result<Self, CoreError> {
        config.validate()?;

        let scheduler = DagScheduler::with_memory_limits(
            config.max_loaded_nodes,
            config.memory_budget_bytes,
        );

        Ok(Self {
            config,
            status: OrchestratorStatus::Initialized,
            catalog: Arc::new(RwLock::new(NodeCatalog::new())),
            executors: Arc::new(RwLock::new(NodeExecutorRegistry::new())),
            scheduler: Arc::new(RwLock::new(scheduler)),
            fractal_loader: FractalLoader::new(),
            policy_engine: PolicyEngine::new(),
            router: RequestRouter::new(),
            sessions: SessionStore::new(OrchestratorConfig::default().max_sessions),
            workflow_definitions: HashMap::new(),
            clock_ms: 0,
        })
    }

    /// Creates an orchestrator with default configuration.
    pub fn with_defaults() -> Result<Self, CoreError> {
        Self::new(OrchestratorConfig::default())
    }

    /// Returns the next monotonic timestamp and advances the clock.
    pub(crate) fn next_timestamp(&mut self) -> u64 {
        let ts = self.clock_ms;
        self.clock_ms += 1;
        ts
    }
}
