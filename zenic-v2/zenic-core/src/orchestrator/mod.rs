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

pub mod coordinator;
pub mod lifecycle;
pub mod types;

// Re-export all public symbols so that external import paths remain
// identical to the old single-file module (e.g. `crate::orchestrator::Orchestrator`).
pub use types::{Orchestrator, OrchestratorStatus};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, RwLock};
    use zenic_flow::WorkflowStep;
    use zenic_graph::{DirectedAcyclicGraph, EdgeDescriptor};
    use zenic_policy::{Action, CriticalityClearance, Permission, Resource, RolePriority, SafetyVeto};
    use zenic_proto::BusinessDomain;
    use zenic_runtime::{DEFAULT_MAX_LOADED_NODES, DEFAULT_MEMORY_BUDGET_BYTES, MemoryManager};

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

    fn setup_orchestrator_with_session() -> (Orchestrator, zenic_proto::SessionId, zenic_proto::TenantId) {
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
        let tid = zenic_proto::TenantId::new();
        let session = orch.create_session(tid).expect("create session");
        let sid = session.session_id;

        // Assign role to session.
        orch.assign_role(role_id, sid, tid).expect("assign role");

        (orch, sid, tid)
    }

    fn make_node(catalog: &Arc<RwLock<zenic_graph::NodeCatalog>>, name: &str) -> zenic_proto::NodeId {
        let id = zenic_proto::NodeId::new();
        catalog.write().unwrap()
            .register_node(zenic_graph::NodeDescriptor {
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

        let id = zenic_proto::NodeId::new();
        orch.register_node(zenic_graph::NodeDescriptor {
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
        let id = zenic_proto::NodeId::new();
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
        let sid = zenic_proto::SessionId::new();
        let tid = zenic_proto::TenantId::new();

        let mut dag = DirectedAcyclicGraph::new();
        dag.add_node(zenic_proto::NodeId::new()).expect("add node");

        let result = orch.execute_dag(&dag, sid, tid);
        assert!(result.is_err());
    }

    // -- Workflow tests --

    #[test]
    fn register_workflow_and_count() {
        let mut orch = Orchestrator::with_defaults().expect("create");
        orch.start().expect("start");

        let wf_id = zenic_proto::WorkflowId::new();
        let steps = vec![WorkflowStep::new("step_1", "First step")];
        let definition = zenic_flow::WorkflowDefinition::new(
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
        let mm = orch.memory_manager();
        let mm_guard = mm.read().expect("lock");
        assert_eq!(mm_guard.max_loaded_nodes(), DEFAULT_MAX_LOADED_NODES);
    }

    // -- Operational check tests --

    #[test]
    fn operations_fail_after_shutdown() {
        let mut orch = Orchestrator::with_defaults().expect("create");
        orch.shutdown().expect("shutdown");

        let result = orch.create_session(zenic_proto::TenantId::new());
        assert!(result.is_err());
    }
}
