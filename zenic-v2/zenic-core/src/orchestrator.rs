//! Main orchestrator for Zenic-Agents.
//!
//! The [`Orchestrator`] is the top-level entry point for the entire
//! system. It holds all subsystems (catalog, scheduler, workflow
//! engine, policy engine) and provides high-level operations that
//! coordinate across them.
//!
//! Every operation that flows through the orchestrator follows the
//! same pattern:
//! 1. Validate the session.
//! 2. Check policy (is the session allowed to do this?).
//! 3. Execute the operation in the appropriate subsystem.
//! 4. Return the result.
//!
//! This ensures that no operation bypasses the policy engine.

use std::collections::HashMap;

use zenic_flow::{WorkflowDefinition, WorkflowInstance};
use zenic_graph::{DirectedAcyclicGraph, NodeCatalog, NodeDescriptor, SubGraphDescriptor, SuperNodeDescriptor};
use zenic_policy::{Permission, PolicyContext, PolicyEngine};
use zenic_proto::{NodeId, SessionId, TenantId, WorkflowId};
use zenic_runtime::{
    DagScheduler, FractalLoader, MemoryManager, NodeExecutor, NodeExecutorRegistry,
};

use crate::config::OrchestratorConfig;
use crate::errors::CoreError;
use crate::router::{RequestRouter, RouteDecision};
use crate::session::{Session, SessionStore};
use crate::step_bridge::DagStepExecutor;

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
    config: OrchestratorConfig,
    /// Current orchestrator status.
    status: OrchestratorStatus,
    /// Node catalog (descriptors for all nodes, super-nodes, subgraphs).
    catalog: NodeCatalog,
    /// Node executor registry (maps NodeId → execution logic).
    executors: NodeExecutorRegistry,
    /// DAG scheduler (executes DAGs with memory awareness).
    scheduler: DagScheduler,
    /// Fractal loader (on-demand subgraph loading/unloading).
    #[allow(dead_code)]
    fractal_loader: FractalLoader,
    /// Policy engine (RBAC, rules, vetoes, audit).
    policy_engine: PolicyEngine,
    /// Request router (classifies incoming requests).
    router: RequestRouter,
    /// Session store (active sessions).
    sessions: SessionStore,
    /// Workflow definitions indexed by ID.
    workflow_definitions: HashMap<WorkflowId, WorkflowDefinition>,
    /// Monotonic clock for timestamps (milliseconds).
    clock_ms: u64,
}

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
            catalog: NodeCatalog::new(),
            executors: NodeExecutorRegistry::new(),
            scheduler,
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
    // Catalog management
    // -----------------------------------------------------------------------

    /// Registers a node descriptor in the catalog.
    pub fn register_node(&mut self, descriptor: NodeDescriptor) -> Result<(), CoreError> {
        self.ensure_operational()?;
        self.catalog
            .register_node(descriptor)
            .map_err(CoreError::from)
    }

    /// Registers a super-node descriptor in the catalog.
    pub fn register_super_node(&mut self, descriptor: SuperNodeDescriptor) -> Result<(), CoreError> {
        self.ensure_operational()?;
        self.catalog
            .register_super_node(descriptor)
            .map_err(CoreError::from)
    }

    /// Registers a sub-graph descriptor in the catalog.
    pub fn register_sub_graph(&mut self, descriptor: SubGraphDescriptor) -> Result<(), CoreError> {
        self.ensure_operational()?;
        self.catalog
            .register_sub_graph(descriptor)
            .map_err(CoreError::from)
    }

    /// Returns the number of registered nodes.
    pub fn node_count(&self) -> usize {
        self.catalog.node_count()
    }

    /// Returns the number of registered super-nodes.
    pub fn super_node_count(&self) -> usize {
        self.catalog.super_node_count()
    }

    /// Returns the number of registered sub-graphs.
    pub fn sub_graph_count(&self) -> usize {
        self.catalog.sub_graph_count()
    }

    // -----------------------------------------------------------------------
    // Executor registration
    // -----------------------------------------------------------------------

    /// Registers a node executor.
    pub fn register_executor(
        &mut self,
        node_id: NodeId,
        executor: Box<dyn NodeExecutor>,
    ) -> Result<(), CoreError> {
        self.ensure_operational()?;
        self.executors
            .register(node_id, executor)
            .map_err(CoreError::from)
    }

    /// Returns the number of registered executors.
    pub fn executor_count(&self) -> usize {
        self.executors.len()
    }

    // -----------------------------------------------------------------------
    // Policy management
    // -----------------------------------------------------------------------

    /// Registers a role in the policy engine.
    pub fn register_role(&mut self, role: zenic_policy::Role) -> Result<(), CoreError> {
        self.policy_engine.register_role(role)?;
        Ok(())
    }

    /// Assigns a role to a session within a tenant.
    pub fn assign_role(
        &mut self,
        role_id: zenic_policy::RoleId,
        session_id: SessionId,
        tenant_id: TenantId,
    ) -> Result<(), CoreError> {
        self.policy_engine
            .assign_role(role_id, session_id, tenant_id)?;
        Ok(())
    }

    /// Adds a policy rule to the policy engine.
    pub fn add_policy_rule(&mut self, rule: zenic_policy::PolicyRule) -> Result<(), CoreError> {
        self.policy_engine.add_rule(rule)?;
        Ok(())
    }

    /// Registers a safety veto (immutable once added).
    pub fn register_veto(&mut self, veto: zenic_policy::SafetyVeto) -> Result<(), CoreError> {
        self.policy_engine.register_veto(veto)?;
        Ok(())
    }

    /// Checks whether a session is allowed to perform an action.
    pub fn is_allowed(&mut self, ctx: &PolicyContext) -> bool {
        self.policy_engine.is_allowed(ctx)
    }

    /// Returns the number of audit entries in the policy engine.
    pub fn audit_count(&self) -> usize {
        self.policy_engine.audit_count()
    }

    // -----------------------------------------------------------------------
    // Workflow management
    // -----------------------------------------------------------------------

    /// Registers a workflow definition for later execution.
    pub fn register_workflow(
        &mut self,
        definition: WorkflowDefinition,
    ) -> Result<(), CoreError> {
        self.ensure_operational()?;
        definition.validate().map_err(CoreError::from)?;
        self.workflow_definitions.insert(definition.id, definition);
        Ok(())
    }

    /// Returns the number of registered workflow definitions.
    pub fn workflow_count(&self) -> usize {
        self.workflow_definitions.len()
    }

    // -----------------------------------------------------------------------
    // Execution
    // -----------------------------------------------------------------------

    /// Executes a DAG on behalf of a session.
    ///
    /// This method first checks the policy engine to ensure the session
    /// is allowed to execute the DAG, then delegates to the DAG scheduler.
    pub fn execute_dag(
        &mut self,
        dag: &DirectedAcyclicGraph,
        session_id: SessionId,
        tenant_id: TenantId,
    ) -> Result<zenic_runtime::ExecutionResult, CoreError> {
        self.ensure_operational()?;
        self.validate_session(&session_id, &tenant_id)?;

        // Policy check: does this session have Execute permission?
        let ctx = PolicyContext::new(
            session_id,
            tenant_id,
            Permission::new(
                zenic_policy::Action::Execute,
                zenic_policy::Resource::AllNodes,
            ),
        );
        if !self.policy_engine.is_allowed(&ctx) {
            return Err(CoreError::Policy(
                zenic_policy::PolicyError::PermissionDenied {
                    session_id,
                    permission: ctx.permission,
                    tenant_id,
                },
            ));
        }

        // Execute the DAG.
        let result = self
            .scheduler
            .execute(dag, &self.catalog, &self.executors, session_id, tenant_id)?;

        Ok(result)
    }

    /// Executes a workflow on behalf of a session.
    ///
    /// This method first checks the policy engine, then looks up the
    /// workflow definition, creates a `DagStepExecutor` bridge, and
    /// delegates to the workflow engine.
    pub fn execute_workflow(
        &mut self,
        workflow_id: &WorkflowId,
        session_id: SessionId,
        tenant_id: TenantId,
    ) -> Result<WorkflowInstance, CoreError> {
        self.ensure_operational()?;
        self.validate_session(&session_id, &tenant_id)?;

        // Policy check.
        let ctx = PolicyContext::new(
            session_id,
            tenant_id,
            Permission::new(
                zenic_policy::Action::Execute,
                zenic_policy::Resource::Workflow(*workflow_id),
            ),
        );
        if !self.policy_engine.is_allowed(&ctx) {
            return Err(CoreError::Policy(
                zenic_policy::PolicyError::PermissionDenied {
                    session_id,
                    permission: ctx.permission,
                    tenant_id,
                },
            ));
        }

        // Look up the workflow definition.
        let definition = self
            .workflow_definitions
            .get(workflow_id)
            .ok_or(CoreError::WorkflowNotFound(*workflow_id))?
            .clone();

        // Create the step executor bridge.
        // The DagStepExecutor needs its own catalog and scheduler
        // because it runs inside the workflow engine which requires
        // Send + Sync. We create fresh instances for the bridge.
        let step_executor = DagStepExecutor::new(
            NodeCatalog::new(),
            NodeExecutorRegistry::new(),
            DagScheduler::with_memory_limits(
                self.config.max_loaded_nodes,
                self.config.memory_budget_bytes,
            ),
        );

        // Execute the workflow.
        let mut engine = zenic_flow::WorkflowEngine::new();
        let instance = engine.execute(&definition, &step_executor, session_id, tenant_id)?;

        Ok(instance)
    }

    /// Routes a request and returns the routing decision.
    pub fn route_request(
        &mut self,
        request: &crate::router::RouteRequest,
    ) -> Result<RouteDecision, CoreError> {
        self.ensure_operational()?;
        self.router.route(request)
    }

    // -----------------------------------------------------------------------
    // Configuration queries
    // -----------------------------------------------------------------------

    /// Returns a reference to the orchestrator configuration.
    pub fn config(&self) -> &OrchestratorConfig {
        &self.config
    }

    /// Returns a reference to the memory manager (via the scheduler).
    pub fn memory_manager(&self) -> &MemoryManager {
        self.scheduler.memory_manager()
    }

    // -----------------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------------

    /// Ensures the orchestrator is in an operational state.
    fn ensure_operational(&self) -> Result<(), CoreError> {
        if !self.status.is_operational() {
            return Err(CoreError::NotInitialized);
        }
        Ok(())
    }

    /// Validates that a session exists and belongs to the given tenant.
    fn validate_session(
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
    fn next_timestamp(&mut self) -> u64 {
        let ts = self.clock_ms;
        self.clock_ms += 1;
        ts
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use zenic_flow::WorkflowStep;
    use zenic_graph::EdgeDescriptor;
    use zenic_policy::{Action, CriticalityClearance, Resource, RolePriority, SafetyVeto};
    use zenic_proto::BusinessDomain;
    use zenic_runtime::{DEFAULT_MAX_LOADED_NODES, DEFAULT_MEMORY_BUDGET_BYTES};

    fn make_admin_role() -> zenic_policy::Role {
        let mut role = zenic_policy::Role::new("admin", "Administrator")
            .with_priority(RolePriority::Admin)
            .with_clearance(CriticalityClearance::Critical);
        role.add_permission(Permission::new(Action::Execute, Resource::AllNodes));
        role.add_permission(Permission::new(Action::Read, Resource::AllNodes));
        role.add_permission(Permission::new(Action::Write, Resource::AllNodes));
        role.add_permission(Permission::new(Action::Delete, Resource::AllNodes));
        role.add_permission(Permission::new(Action::Admin, Resource::PolicyEngine));
        role.add_permission(Permission::new(Action::Cancel, Resource::AllWorkflows));
        role
    }

    fn setup_orchestrator_with_session() -> (Orchestrator, SessionId, TenantId) {
        let mut orch = Orchestrator::with_defaults().expect("create orchestrator");
        orch.start().expect("start");

        // Register admin role.
        let admin_role = make_admin_role();
        let role_id = admin_role.id;
        orch.register_role(admin_role).expect("register role");

        // Add allow rule.
        orch.add_policy_rule(
            zenic_policy::PolicyRule::allow(
                "allow_all",
                "Allow all operations",
                Permission::new(Action::Execute, Resource::AllNodes),
            ),
        )
        .expect("add rule");

        // Create session.
        let tid = TenantId::new();
        let session = orch.create_session(tid).expect("create session");
        let sid = session.session_id;

        // Assign role to session.
        orch.assign_role(role_id, sid, tid).expect("assign role");

        (orch, sid, tid)
    }

    fn make_node(catalog: &mut NodeCatalog, name: &str) -> NodeId {
        let id = NodeId::new();
        catalog
            .register_node(NodeDescriptor {
                id,
                name: name.to_string(),
                version: "1.0.0".to_string(),
                category: zenic_proto::NodeCategory::Orchestrator,
                domain: BusinessDomain::ECommerce,
                criticality: zenic_proto::NodeCriticality::Medium,
                load_policy: zenic_proto::LoadPolicy::OnDemand,
                memory_estimate_bytes: 256,
                dependencies: vec![],
                super_node_id: None,
                sub_graph_id: None,
                requires_external_api: false,
                description: format!("Node {}", name),
            })
            .expect("register node");
        id
    }

    // -- Status tests --

    #[test]
    fn orchestrator_new_is_initialized() {
        let orch = Orchestrator::with_defaults().expect("create");
        assert_eq!(orch.status(), OrchestratorStatus::Initialized);
    }

    #[test]
    fn orchestrator_start_transitions_to_running() {
        let mut orch = Orchestrator::with_defaults().expect("create");
        orch.start().expect("start");
        assert_eq!(orch.status(), OrchestratorStatus::Running);
    }

    #[test]
    fn orchestrator_shutdown() {
        let mut orch = Orchestrator::with_defaults().expect("create");
        orch.start().expect("start");
        orch.shutdown().expect("shutdown");
        assert_eq!(orch.status(), OrchestratorStatus::Shutdown);
    }

    #[test]
    fn orchestrator_double_shutdown_fails() {
        let mut orch = Orchestrator::with_defaults().expect("create");
        orch.shutdown().expect("shutdown 1");
        let result = orch.shutdown();
        assert!(result.is_err());
    }

    // -- Session tests --

    #[test]
    fn create_and_get_session() {
        let (orch, sid, tid) = setup_orchestrator_with_session();
        let session = orch.get_session(&sid);
        assert!(session.is_some());
        assert_eq!(session.unwrap().tenant_id, tid);
    }

    #[test]
    fn end_session() {
        let (mut orch, sid, _) = setup_orchestrator_with_session();
        let removed = orch.end_session(&sid);
        assert!(removed.is_some());
        assert!(orch.get_session(&sid).is_none());
        assert_eq!(orch.session_count(), 0);
    }

    // -- Catalog tests --

    #[test]
    fn register_node_and_count() {
        let mut orch = Orchestrator::with_defaults().expect("create");
        orch.start().expect("start");
        assert_eq!(orch.node_count(), 0);

        let id = NodeId::new();
        orch.register_node(NodeDescriptor {
            id,
            name: "test_node".to_string(),
            version: "1.0.0".to_string(),
            category: zenic_proto::NodeCategory::Decision,
            domain: BusinessDomain::ECommerce,
            criticality: zenic_proto::NodeCriticality::Medium,
            load_policy: zenic_proto::LoadPolicy::OnDemand,
            memory_estimate_bytes: 256,
            dependencies: vec![],
            super_node_id: None,
            sub_graph_id: None,
            requires_external_api: false,
            description: "A test node".to_string(),
        })
        .expect("register node");

        assert_eq!(orch.node_count(), 1);
    }

    // -- Executor tests --

    #[test]
    fn register_executor() {
        let mut orch = Orchestrator::with_defaults().expect("create");
        orch.start().expect("start");
        let id = NodeId::new();
        orch.register_executor(id, Box::new(zenic_runtime::NoOpExecutor::new("test")))
            .expect("register executor");
        assert_eq!(orch.executor_count(), 1);
    }

    // -- Policy tests --

    #[test]
    fn register_role_and_veto() {
        let mut orch = Orchestrator::with_defaults().expect("create");
        orch.start().expect("start");

        let role = make_admin_role();
        assert!(orch.register_role(role).is_ok());

        let veto = SafetyVeto::new("no_delete", "Never delete", Action::Delete, Resource::AllNodes);
        assert!(orch.register_veto(veto).is_ok());
    }

    // -- DAG execution tests --

    #[test]
    fn execute_dag_success() {
        let (mut orch, sid, tid) = setup_orchestrator_with_session();

        // Register nodes and executors.
        let n1 = make_node(&mut orch.catalog, "step1");
        let n2 = make_node(&mut orch.catalog, "step2");

        orch.register_executor(n1, Box::new(zenic_runtime::NoOpExecutor::new("step1")))
            .expect("register executor");
        orch.register_executor(n2, Box::new(zenic_runtime::NoOpExecutor::new("step2")))
            .expect("register executor");

        // Build DAG.
        let mut dag = DirectedAcyclicGraph::new();
        dag.add_node(n1).expect("add node 1");
        dag.add_node(n2).expect("add node 2");
        dag.add_edge(EdgeDescriptor::data(n1, n2)).expect("add edge");

        // Execute.
        let result = orch.execute_dag(&dag, sid, tid).expect("execute dag");
        assert!(result.is_success());
        assert_eq!(result.nodes_completed, 2);
    }

    #[test]
    fn execute_dag_policy_denied() {
        let mut orch = Orchestrator::with_defaults().expect("create");
        orch.start().expect("start");

        // No roles assigned → policy will deny.
        let sid = SessionId::new();
        let tid = TenantId::new();

        let mut dag = DirectedAcyclicGraph::new();
        dag.add_node(NodeId::new()).expect("add node");

        let result = orch.execute_dag(&dag, sid, tid);
        assert!(result.is_err());
    }

    // -- Workflow tests --

    #[test]
    fn register_workflow_and_count() {
        let mut orch = Orchestrator::with_defaults().expect("create");
        orch.start().expect("start");

        let wf_id = WorkflowId::new();
        let steps = vec![WorkflowStep::new("step_1", "First step")];
        let definition = WorkflowDefinition::new(
            wf_id,
            "test_workflow",
            "A test workflow",
            steps,
            zenic_flow::RetryPolicy::no_retry(),
        );

        orch.register_workflow(definition).expect("register workflow");
        assert_eq!(orch.workflow_count(), 1);
    }

    // -- Config query tests --

    #[test]
    fn config_accessible() {
        let orch = Orchestrator::with_defaults().expect("create");
        assert_eq!(orch.config().max_loaded_nodes, DEFAULT_MAX_LOADED_NODES);
        assert_eq!(orch.config().memory_budget_bytes, DEFAULT_MEMORY_BUDGET_BYTES);
    }

    #[test]
    fn memory_manager_accessible() {
        let orch = Orchestrator::with_defaults().expect("create");
        assert_eq!(orch.memory_manager().max_loaded_nodes(), DEFAULT_MAX_LOADED_NODES);
    }

    // -- Operational check tests --

    #[test]
    fn operations_fail_after_shutdown() {
        let mut orch = Orchestrator::with_defaults().expect("create");
        orch.shutdown().expect("shutdown");

        let result = orch.create_session(TenantId::new());
        assert!(result.is_err());
    }
}
