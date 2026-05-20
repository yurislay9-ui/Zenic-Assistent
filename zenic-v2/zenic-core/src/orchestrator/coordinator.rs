//! Orchestrator coordination: catalog, executor, policy, workflow,
//! and execution methods that delegate across subsystems.

use std::sync::Arc;

use zenic_flow::WorkflowInstance;
use zenic_graph::{DirectedAcyclicGraph, NodeDescriptor, SubGraphDescriptor, SuperNodeDescriptor};
use zenic_policy::{Permission, PolicyContext};
use zenic_proto::{NodeId, SessionId, TenantId, WorkflowId};

use crate::errors::CoreError;
use crate::router::RouteDecision;
use crate::step_bridge::DagStepExecutor;

use super::types::Orchestrator;

impl Orchestrator {
    // -----------------------------------------------------------------------
    // Catalog management
    // -----------------------------------------------------------------------

    /// Registers a node descriptor in the catalog.
    pub fn register_node(&mut self, descriptor: NodeDescriptor) -> Result<(), CoreError> {
        self.ensure_operational()?;
        let mut catalog = self.catalog.write().map_err(|e| {
            CoreError::Validation(format!("catalog lock poisoned: {}", e))
        })?;
        catalog.register_node(descriptor).map_err(CoreError::from)
    }

    /// Registers a super-node descriptor in the catalog.
    pub fn register_super_node(&mut self, descriptor: SuperNodeDescriptor) -> Result<(), CoreError> {
        self.ensure_operational()?;
        let mut catalog = self.catalog.write().map_err(|e| {
            CoreError::Validation(format!("catalog lock poisoned: {}", e))
        })?;
        catalog.register_super_node(descriptor).map_err(CoreError::from)
    }

    /// Registers a sub-graph descriptor in the catalog.
    pub fn register_sub_graph(&mut self, descriptor: SubGraphDescriptor) -> Result<(), CoreError> {
        self.ensure_operational()?;
        let mut catalog = self.catalog.write().map_err(|e| {
            CoreError::Validation(format!("catalog lock poisoned: {}", e))
        })?;
        catalog.register_sub_graph(descriptor).map_err(CoreError::from)
    }

    /// Returns the number of registered nodes.
    pub fn node_count(&self) -> usize {
        self.catalog.read().map(|c| c.node_count()).unwrap_or(0)
    }

    /// Returns the number of registered super-nodes.
    pub fn super_node_count(&self) -> usize {
        self.catalog.read().map(|c| c.super_node_count()).unwrap_or(0)
    }

    /// Returns the number of registered sub-graphs.
    pub fn sub_graph_count(&self) -> usize {
        self.catalog.read().map(|c| c.sub_graph_count()).unwrap_or(0)
    }

    // -----------------------------------------------------------------------
    // Executor registration
    // -----------------------------------------------------------------------

    /// Registers a node executor.
    pub fn register_executor(
        &mut self,
        node_id: NodeId,
        executor: Box<dyn zenic_runtime::NodeExecutor>,
    ) -> Result<(), CoreError> {
        self.ensure_operational()?;
        let mut executors = self.executors.write().map_err(|e| {
            CoreError::Validation(format!("executors lock poisoned: {}", e))
        })?;
        executors.register(node_id, executor).map_err(CoreError::from)
    }

    /// Returns the number of registered executors.
    pub fn executor_count(&self) -> usize {
        self.executors.read().map(|e| e.len()).unwrap_or(0)
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
        definition: zenic_flow::WorkflowDefinition,
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

        // Execute the DAG with shared catalog and executors.
        // Write lock required because DagScheduler::execute takes &mut self.
        let mut scheduler = self.scheduler.write().map_err(|e| {
            CoreError::Validation(format!("scheduler lock poisoned: {}", e))
        })?;
        let catalog = self.catalog.read().map_err(|e| {
            CoreError::Validation(format!("catalog lock poisoned: {}", e))
        })?;
        let executors = self.executors.read().map_err(|e| {
            CoreError::Validation(format!("executors lock poisoned: {}", e))
        })?;
        let result = scheduler.execute(dag, &catalog, &executors, session_id, tenant_id)?;

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

        // E-09 FIX: Share the orchestrator's populated catalog and executor
        // registry with the DagStepExecutor via Arc<RwLock<>>. Previously,
        // empty instances were created, causing "subgraph not found" errors
        // for any workflow step that referenced a subgraph.
        let step_executor = DagStepExecutor::with_context(
            Arc::clone(&self.catalog),
            Arc::clone(&self.executors),
            Arc::clone(&self.scheduler),
            session_id,
            tenant_id,
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
}
