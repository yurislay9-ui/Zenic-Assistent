//! DAG scheduler with topological execution and memory awareness.
//!
//! The [`DagScheduler`] orchestrates a single execution run of a DAG.
//! It walks the graph in topological order, ensuring that predecessor
//! outputs are available before executing each node.

use std::time::Instant;
use zenic_graph::{DirectedAcyclicGraph, NodeCatalog};
use zenic_proto::{ExecutionId, NodeId, SessionId, TenantId};

use crate::context::ExecutionContext;
use crate::errors::RuntimeError;
use crate::executor::NodeExecutorRegistry;
use crate::memory::MemoryManager;
use crate::result::{ExecutionResult, NodeResult};

// ---------------------------------------------------------------------------
// DagScheduler
// ---------------------------------------------------------------------------

/// Orchestrates a single execution run of a DAG.
///
/// The scheduler:
/// 1. Computes the topological order of the DAG.
/// 2. For each node in order, loads it into RAM (if not already loaded).
/// 3. Collects inputs from predecessor outputs.
/// 4. Executes the node through the executor registry.
/// 5. Stores the output in the execution context.
/// 6. Evicts idle nodes when memory is pressured.
///
/// If a node fails, all downstream nodes are marked as skipped.
pub struct DagScheduler {
    /// Memory manager for load/evict decisions.
    memory_manager: MemoryManager,
}

impl DagScheduler {
    /// Creates a new scheduler with default memory limits.
    pub fn new() -> Self {
        Self {
            memory_manager: MemoryManager::new(),
        }
    }

    /// Creates a new scheduler with custom memory limits.
    pub fn with_memory_limits(max_nodes: usize, budget_bytes: u64) -> Self {
        Self {
            memory_manager: MemoryManager::with_limits(max_nodes, budget_bytes),
        }
    }

    /// Returns a reference to the memory manager.
    pub fn memory_manager(&self) -> &MemoryManager {
        &self.memory_manager
    }

    /// Executes a DAG run.
    ///
    /// # Arguments
    ///
    /// - `dag`: The directed acyclic graph to execute.
    /// - `catalog`: Node descriptor catalog (provides names, memory estimates, load policies).
    /// - `executors`: Registry of node executors.
    /// - `session_id`: The session that initiated this execution.
    /// - `tenant_id`: The tenant that owns this execution.
    pub fn execute(
        &mut self,
        dag: &DirectedAcyclicGraph,
        catalog: &NodeCatalog,
        executors: &NodeExecutorRegistry,
        session_id: SessionId,
        tenant_id: TenantId,
    ) -> Result<ExecutionResult, RuntimeError> {
        let execution_id = ExecutionId::new();
        let start = Instant::now();

        // Step 1: Topological sort.
        let topo_order = dag.topological_sort().map_err(RuntimeError::from)?;

        let mut ctx = ExecutionContext::new(execution_id, session_id, tenant_id);
        let mut result = ExecutionResult::new(execution_id);

        // Step 2: Load always-loaded nodes first.
        for node_id in &topo_order {
            if let Some(desc) = catalog.get_node(node_id) {
                if desc.load_policy == zenic_proto::LoadPolicy::Always {
                    self.memory_manager
                        .load_node(
                            desc.id,
                            desc.memory_estimate_bytes,
                            desc.sub_graph_id,
                            desc.load_policy,
                        )
                        .map_err(|e| RuntimeError::General(format!(
                            "failed to load always-on node {}: {}",
                            desc.name, e
                        )))?;
                }
            }
        }

        // Track which nodes have failed so we can skip their successors.
        let mut failed_nodes: Vec<NodeId> = Vec::new();

        // Step 3: Execute nodes in topological order.
        for node_id in &topo_order {
            let desc = match catalog.get_node(node_id) {
                Some(d) => d,
                None => {
                    return Err(RuntimeError::General(format!(
                        "node {} not found in catalog",
                        node_id
                    )));
                }
            };

            // Check if any predecessor has failed -> skip this node.
            let predecessors = dag.predecessors(node_id);
            let should_skip = predecessors.iter().any(|pred| failed_nodes.contains(pred));

            if should_skip {
                result.add_node_result(NodeResult::skipped(*node_id, desc.name.clone()));
                failed_nodes.push(*node_id);
                continue;
            }

            // Load node into memory if not already loaded.
            if !self.memory_manager.is_loaded(node_id) {
                self.load_node_with_eviction(desc, catalog)?;
            }

            // Mark as executing.
            self.memory_manager.mark_executing(node_id).map_err(|e| {
                RuntimeError::General(format!(
                    "failed to mark node {} as executing: {}",
                    desc.name, e
                ))
            })?;

            // Build input from predecessor outputs.
            let input = ctx.build_node_input(*node_id, &predecessors);

            // Execute.
            let node_result = executors.execute_node(
                node_id,
                &desc.name,
                &input,
                desc.memory_estimate_bytes,
            );

            // Mark as completed (no longer executing).
            let _ = self.memory_manager.mark_completed(node_id);

            // Store output in context if successful.
            if node_result.is_success() {
                // Build a NodeOutput from the executor.
                // For now, we create a simple empty success output since
                // the executor returns the result separately.
                ctx.store_output(crate::context::NodeOutput::empty_success(*node_id));
            } else {
                failed_nodes.push(*node_id);
            }

            result.add_node_result(node_result);
        }

        let total_duration = start.elapsed();
        let peak_memory = self.memory_manager.current_usage_bytes();
        result.finalize(total_duration, peak_memory);

        Ok(result)
    }

    // -----------------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------------

    /// Loads a node, evicting LRU nodes if necessary.
    fn load_node_with_eviction(
        &mut self,
        desc: &zenic_graph::NodeDescriptor,
        _catalog: &NodeCatalog,
    ) -> Result<(), RuntimeError> {
        // Try direct load first.
        let load_result = self.memory_manager.load_node(
            desc.id,
            desc.memory_estimate_bytes,
            desc.sub_graph_id,
            desc.load_policy,
        );

        if load_result.is_ok() {
            return Ok(());
        }

        // Need to evict. Find LRU candidates and evict until we have room.
        let mut evicted = 0usize;
        loop {
            let candidate = self.memory_manager.find_lru_eviction_candidate();
            match candidate {
                Some(node_id) => {
                    self.memory_manager.evict_node(&node_id)?;
                    evicted += 1;
                }
                None => {
                    return Err(RuntimeError::General(format!(
                        "cannot free memory for node {}: no evictable nodes",
                        desc.name
                    )));
                }
            }

            // Try loading again.
            if self.memory_manager.load_node(
                desc.id,
                desc.memory_estimate_bytes,
                desc.sub_graph_id,
                desc.load_policy,
            ).is_ok() {
                return Ok(());
            }

            // Safety limit: don't evict more than 100 nodes in one go.
            if evicted >= 100 {
                return Err(RuntimeError::General(format!(
                    "eviction limit reached while trying to load node {}",
                    desc.name
                )));
            }
        }
    }
}

impl Default for DagScheduler {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::executor::NoOpExecutor;
    use zenic_graph::EdgeDescriptor;
    use zenic_proto::{LoadPolicy, NodeCategory, NodeCriticality, BusinessDomain};

    fn make_node(catalog: &mut NodeCatalog, name: &str, domain: BusinessDomain) -> NodeId {
        let id = NodeId::new();
        let desc = zenic_graph::NodeDescriptor {
            id,
            name: name.to_string(),
            version: "1.0.0".to_string(),
            category: NodeCategory::Orchestrator,
            domain,
            criticality: NodeCriticality::High,
            load_policy: LoadPolicy::OnDemand,
            memory_estimate_bytes: 256,
            dependencies: vec![],
            super_node_id: None,
            sub_graph_id: None,
            requires_external_api: false,
            description: format!("Node {}", name),
        };
        catalog.register_node(desc).expect("register node");
        id
    }

    fn make_dag_with_nodes(ids: &[NodeId]) -> DirectedAcyclicGraph {
        let mut dag = DirectedAcyclicGraph::new();
        for id in ids {
            dag.add_node(*id).expect("add node");
        }
        dag
    }

    #[test]
    fn execute_single_node() {
        let mut catalog = NodeCatalog::new();
        let n1 = make_node(&mut catalog, "root", BusinessDomain::ECommerce);

        let dag = make_dag_with_nodes(&[n1]);

        let mut executors = NodeExecutorRegistry::new();
        executors.register(n1, Box::new(NoOpExecutor::new("root"))).expect("register");

        let mut scheduler = DagScheduler::new();
        let result = scheduler.execute(
            &dag,
            &catalog,
            &executors,
            SessionId::new(),
            TenantId::new(),
        ).expect("execute");

        assert!(result.is_success());
        assert_eq!(result.nodes_completed, 1);
        assert_eq!(result.nodes_failed, 0);
    }

    #[test]
    fn execute_linear_dag() {
        let mut catalog = NodeCatalog::new();
        let n1 = make_node(&mut catalog, "step1", BusinessDomain::ECommerce);
        let n2 = make_node(&mut catalog, "step2", BusinessDomain::ECommerce);
        let n3 = make_node(&mut catalog, "step3", BusinessDomain::ECommerce);

        let mut dag = make_dag_with_nodes(&[n1, n2, n3]);
        dag.add_edge(EdgeDescriptor::data(n1, n2)).expect("edge");
        dag.add_edge(EdgeDescriptor::data(n2, n3)).expect("edge");

        let mut executors = NodeExecutorRegistry::new();
        executors.register(n1, Box::new(NoOpExecutor::new("step1"))).expect("register");
        executors.register(n2, Box::new(NoOpExecutor::new("step2"))).expect("register");
        executors.register(n3, Box::new(NoOpExecutor::new("step3"))).expect("register");

        let mut scheduler = DagScheduler::new();
        let result = scheduler.execute(
            &dag,
            &catalog,
            &executors,
            SessionId::new(),
            TenantId::new(),
        ).expect("execute");

        assert!(result.is_success());
        assert_eq!(result.nodes_completed, 3);
    }

    #[test]
    fn execute_diamond_dag() {
        let mut catalog = NodeCatalog::new();
        let root = make_node(&mut catalog, "root", BusinessDomain::ECommerce);
        let left = make_node(&mut catalog, "left", BusinessDomain::ECommerce);
        let right = make_node(&mut catalog, "right", BusinessDomain::ECommerce);
        let sink = make_node(&mut catalog, "sink", BusinessDomain::ECommerce);

        let mut dag = make_dag_with_nodes(&[root, left, right, sink]);
        dag.add_edge(EdgeDescriptor::data(root, left)).expect("edge");
        dag.add_edge(EdgeDescriptor::data(root, right)).expect("edge");
        dag.add_edge(EdgeDescriptor::data(left, sink)).expect("edge");
        dag.add_edge(EdgeDescriptor::data(right, sink)).expect("edge");

        let mut executors = NodeExecutorRegistry::new();
        executors.register(root, Box::new(NoOpExecutor::new("root"))).expect("register");
        executors.register(left, Box::new(NoOpExecutor::new("left"))).expect("register");
        executors.register(right, Box::new(NoOpExecutor::new("right"))).expect("register");
        executors.register(sink, Box::new(NoOpExecutor::new("sink"))).expect("register");

        let mut scheduler = DagScheduler::new();
        let result = scheduler.execute(
            &dag,
            &catalog,
            &executors,
            SessionId::new(),
            TenantId::new(),
        ).expect("execute");

        assert!(result.is_success());
        assert_eq!(result.nodes_completed, 4);
    }

    #[test]
    fn scheduler_default_is_new() {
        let _scheduler = DagScheduler::default();
    }
}
