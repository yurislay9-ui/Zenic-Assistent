//! Orchestrator lifecycle: construction, start/shutdown, session management,
//! configuration queries, and private helpers.

use std::sync::{Arc, RwLock};

use zenic_graph::NodeCatalog;
use zenic_proto::{SessionId, TenantId};
use zenic_runtime::{DagScheduler, FractalLoader, MemoryManager, NodeExecutorRegistry};

use crate::config::OrchestratorConfig;
use crate::errors::CoreError;
use crate::session::{Session, SessionStore};

use super::types::{Orchestrator, OrchestratorStatus};

impl Orchestrator {
    /// Creates a new orchestrator with the given configuration.
    ///
    /// Validates the configuration before initializing subsystems.
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
            policy_engine: zenic_policy::PolicyEngine::new(),
            router: crate::router::RequestRouter::new(),
            sessions: SessionStore::new(OrchestratorConfig::default().max_sessions),
            workflow_definitions: std::collections::HashMap::new(),
            clock_ms: 0,
        })
    }

    /// Creates an orchestrator with default configuration.
    pub fn with_defaults() -> Result<Self, CoreError> {
        Self::new(OrchestratorConfig::default())
    }

    // -----------------------------------------------------------------------
    // Status
    // -----------------------------------------------------------------------

    /// Returns the current orchestrator status.
    pub fn status(&self) -> OrchestratorStatus {
        self.status
    }

    /// Starts the orchestrator, transitioning to Running state.
    pub fn start(&mut self) -> Result<(), CoreError> {
        if self.status == OrchestratorStatus::Shutdown {
            return Err(CoreError::AlreadyShutdown);
        }
        self.status = OrchestratorStatus::Running;
        Ok(())
    }

    /// Shuts down the orchestrator, releasing all resources.
    pub fn shutdown(&mut self) -> Result<(), CoreError> {
        if self.status == OrchestratorStatus::Shutdown {
            return Err(CoreError::AlreadyShutdown);
        }
        self.status = OrchestratorStatus::Shutdown;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Session management
    // -----------------------------------------------------------------------

    /// Creates a new session for the given tenant.
    ///
    /// Returns the newly created session, or an error if the maximum
    /// session limit has been reached.
    pub fn create_session(&mut self, tenant_id: TenantId) -> Result<Session, CoreError> {
        self.ensure_operational()?;
        let ts = self.next_timestamp();
        self.sessions.create(tenant_id, ts)
    }

    /// Retrieves a session by its ID.
    pub fn get_session(&self, session_id: &SessionId) -> Option<&Session> {
        self.sessions.get(session_id)
    }

    /// Ends a session, removing it from the active sessions.
    pub fn end_session(&mut self, session_id: &SessionId) -> Option<Session> {
        self.sessions.remove(session_id)
    }

    /// Returns the number of active sessions.
    pub fn session_count(&self) -> usize {
        self.sessions.len()
    }

    // -----------------------------------------------------------------------
    // Configuration queries
    // -----------------------------------------------------------------------

    /// Returns a reference to the orchestrator configuration.
    pub fn config(&self) -> &OrchestratorConfig {
        &self.config
    }

    /// Returns a reference to the memory manager (via the scheduler).
    pub fn memory_manager(&self) -> Arc<RwLock<MemoryManager>> {
        // E-09 FIX: Return Arc<RwLock<>> since scheduler is now shared.
        // The caller must acquire the read lock to access the memory manager.
        Arc::new(RwLock::new(self.scheduler.read()
            .map(|s| {
                let mm = s.memory_manager();
                MemoryManager::with_limits(mm.max_loaded_nodes(), mm.memory_budget_bytes())
            })
            .unwrap_or_else(|_| MemoryManager::new())))
    }

    // -----------------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------------

    /// Ensures the orchestrator is in an operational state.
    pub(crate) fn ensure_operational(&self) -> Result<(), CoreError> {
        if !self.status.is_operational() {
            return Err(CoreError::NotInitialized);
        }
        Ok(())
    }

    /// Validates that a session exists and belongs to the given tenant.
    pub(crate) fn validate_session(
        &self,
        session_id: &SessionId,
        tenant_id: &TenantId,
    ) -> Result<(), CoreError> {
        let session = self
            .sessions
            .get(session_id)
            .ok_or(CoreError::SessionNotFound(*session_id))?;
        if session.tenant_id != *tenant_id {
            return Err(CoreError::Validation(format!(
                "session {} does not belong to tenant {}",
                session_id, tenant_id
            )));
        }
        Ok(())
    }

    /// Returns the next monotonic timestamp and advances the clock.
    pub(crate) fn next_timestamp(&mut self) -> u64 {
        let ts = self.clock_ms;
        self.clock_ms += 1;
        ts
    }
}
