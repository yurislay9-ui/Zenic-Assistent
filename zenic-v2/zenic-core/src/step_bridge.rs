//! Bridge between the flow engine's [`StepExecutor`] trait and the
//! runtime's [`DagScheduler`].
//!
//! The [`DagStepExecutor`] implements [`zenic_flow::StepExecutor`] by
//! using the DAG scheduler to execute the subgraph referenced by each
//! workflow step. This bridge is the key integration point between
//! the flow and runtime subsystems: durable workflows delegate actual
//! node execution to the DAG scheduler through this struct.

use std::sync::Mutex;

use zenic_flow::{StepExecutor, WorkflowStep};
use zenic_graph::NodeCatalog;
use zenic_runtime::{DagScheduler, NodeExecutorRegistry};

// ---------------------------------------------------------------------------
// DagStepExecutor
// ---------------------------------------------------------------------------

/// Implements [`StepExecutor`] by delegating to the [`DagScheduler`].
///
/// When a workflow step references a subgraph (`step.sub_graph_id`),
/// this executor loads the subgraph's DAG from the catalog and runs
/// it through the scheduler. Steps without a subgraph reference
/// produce an empty success output (no-op).
///
/// The executor holds references to the catalog and executor registry
/// via `Mutex` so that it can be shared across the workflow engine's
/// internal state machine, which requires `Send + Sync`.
pub struct DagStepExecutor {
    /// The node catalog for DAG resolution.
    catalog: Mutex<NodeCatalog>,
    /// The node executor registry for node execution.
    executors: Mutex<NodeExecutorRegistry>,
    /// The DAG scheduler for running subgraphs.
    scheduler: Mutex<DagScheduler>,
}

impl DagStepExecutor {
    /// Creates a new DAG step executor.
    pub fn new(
        catalog: NodeCatalog,
        executors: NodeExecutorRegistry,
        scheduler: DagScheduler,
    ) -> Self {
        Self {
            catalog: Mutex::new(catalog),
            executors: Mutex::new(executors),
            scheduler: Mutex::new(scheduler),
        }
    }

    /// Creates a minimal executor with empty catalog and no node executors.
    /// Useful for testing or when the executor will be populated later.
    pub fn empty() -> Self {
        Self {
            catalog: Mutex::new(NodeCatalog::new()),
            executors: Mutex::new(NodeExecutorRegistry::new()),
            scheduler: Mutex::new(DagScheduler::new()),
        }
    }
}

impl StepExecutor for DagStepExecutor {
    fn execute_step(
        &self,
        step: &WorkflowStep,
        _input: Option<&[u8]>,
    ) -> Result<Vec<u8>, String> {
        let sub_graph_id = match step.sub_graph_id {
            Some(id) => id,
            None => {
                // No subgraph reference: this is a no-op step.
                return Ok(Vec::new());
            }
        };

        // Look up the subgraph's DAG from the catalog.
        let catalog = self.catalog.lock().map_err(|e| {
            format!("failed to lock catalog: {}", e)
        })?;

        let sub_graph_desc = catalog.get_sub_graph(&sub_graph_id).ok_or_else(|| {
            format!("subgraph {} not found in catalog", sub_graph_id)
        })?;

        // Build a minimal DAG from the subgraph's node IDs.
        // In a full implementation, we would look up the actual DAG
        // structure (edges, topology) from a persistent store.
        // For Phase 5, we construct a simple linear DAG from the
        // subgraph's node list.
        let mut dag = zenic_graph::DirectedAcyclicGraph::new();
        for node_id in &sub_graph_desc.node_ids {
            dag.add_node(*node_id).map_err(|e| format!("{}", e))?;
        }

        // Add edges between consecutive nodes (linear chain).
        for i in 0..sub_graph_desc.node_ids.len().saturating_sub(1) {
            let from = sub_graph_desc.node_ids[i];
            let to = sub_graph_desc.node_ids[i + 1];
            dag.add_edge(zenic_graph::EdgeDescriptor::data(from, to))
                .map_err(|e| format!("{}", e))?;
        }

        // Execute the DAG through the scheduler.
        let mut scheduler = self.scheduler.lock().map_err(|e| {
            format!("failed to lock scheduler: {}", e)
        })?;
        let executors = self.executors.lock().map_err(|e| {
            format!("failed to lock executors: {}", e)
        })?;

        let session_id = zenic_proto::SessionId::new();
        let tenant_id = zenic_proto::TenantId::new();

        let result = scheduler
            .execute(&dag, &catalog, &executors, session_id, tenant_id)
            .map_err(|e| format!("dag execution failed: {}", e))?;

        if result.is_success() {
            // Serialize the execution result as the step output.
            // For simplicity, we return the execution ID as bytes.
            Ok(result.execution_id.to_string().into_bytes())
        } else {
            Err(format!(
                "dag execution failed: {} of {} nodes failed",
                result.nodes_failed,
                result.total_nodes_processed()
            ))
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use zenic_graph::SubGraphDescriptor;
    use zenic_proto::{BusinessDomain, LoadPolicy, NodeCategory, NodeCriticality, NodeId, SubGraphId};

    fn setup_catalog_with_subgraph() -> (NodeCatalog, SubGraphId, Vec<NodeId>) {
        let mut catalog = NodeCatalog::new();
        let sg_id = SubGraphId::new();
        let sn_id = zenic_proto::SuperNodeId::new();

        // Register super-node first (required by catalog validation).
        catalog
            .register_super_node(zenic_graph::SuperNodeDescriptor {
                id: sn_id,
                name: "test_supernode".to_string(),
                domain: BusinessDomain::ECommerce,
                description: "Test super-node".to_string(),
                sub_graph_ids: vec![sg_id],
                criticality: NodeCriticality::Medium,
                load_policy: LoadPolicy::OnDemand,
                memory_estimate_bytes: 1024,
                max_active_subgraphs: 1,
            })
            .expect("register super-node");

        // Create nodes.
        let n1 = NodeId::new();
        let n2 = NodeId::new();

        for (id, name) in [(n1, "step_a"), (n2, "step_b")] {
            catalog
                .register_node(zenic_graph::NodeDescriptor {
                    id,
                    name: name.to_string(),
                    version: "1.0.0".to_string(),
                    category: NodeCategory::Decision,
                    domain: BusinessDomain::ECommerce,
                    criticality: NodeCriticality::Medium,
                    load_policy: LoadPolicy::OnDemand,
                    memory_estimate_bytes: 256,
                    dependencies: vec![],
                    super_node_id: Some(sn_id),
                    sub_graph_id: Some(sg_id),
                    requires_external_api: false,
                    description: format!("Node {}", name),
                })
                .expect("register node");
        }

        // Create subgraph.
        catalog
            .register_sub_graph(SubGraphDescriptor {
                id: sg_id,
                name: "test_subgraph".to_string(),
                domain: BusinessDomain::ECommerce,
                description: "Test subgraph".to_string(),
                super_node_id: sn_id,
                node_ids: vec![n1, n2],
                entry_node_ids: vec![n1],
                exit_node_ids: vec![n2],
                load_policy: LoadPolicy::OnDemand,
                criticality: NodeCriticality::Medium,
                memory_estimate_bytes: 512,
                version: "1.0.0".to_string(),
            })
            .expect("register subgraph");

        (catalog, sg_id, vec![n1, n2])
    }

    #[test]
    fn step_executor_no_subgraph_is_noop() {
        let executor = DagStepExecutor::empty();
        let step = WorkflowStep::new("noop_step", "No subgraph");
        let result = executor.execute_step(&step, None);
        assert!(result.is_ok());
        assert!(result.unwrap().is_empty());
    }

    #[test]
    fn step_executor_with_subgraph() {
        let (catalog, sg_id, nodes) = setup_catalog_with_subgraph();

        let mut executors = NodeExecutorRegistry::new();
        for id in &nodes {
            executors
                .register(*id, Box::new(zenic_runtime::NoOpExecutor::new("noop")))
                .expect("register");
        }

        let scheduler = DagScheduler::with_memory_limits(25, 50 * 1024 * 1024);
        let executor = DagStepExecutor::new(catalog, executors, scheduler);

        let step = WorkflowStep::with_sub_graph("test_step", "Test", sg_id);
        let result = executor.execute_step(&step, None);
        assert!(result.is_ok());
        assert!(!result.unwrap().is_empty());
    }

    #[test]
    fn step_executor_missing_subgraph() {
        let executor = DagStepExecutor::empty();
        let sg_id = SubGraphId::new();
        let step = WorkflowStep::with_sub_graph("missing", "Missing", sg_id);
        let result = executor.execute_step(&step, None);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("not found"));
    }

    #[test]
    fn empty_executor_creates_minimal() {
        let executor = DagStepExecutor::empty();
        let step = WorkflowStep::new("simple", "Simple step");
        let result = executor.execute_step(&step, None);
        assert!(result.is_ok());
    }
}
