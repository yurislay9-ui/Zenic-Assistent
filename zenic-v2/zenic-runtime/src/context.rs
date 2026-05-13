//! Execution context for DAG runs.
//!
//! [`ExecutionContext`] carries typed data through the DAG during a single
//! execution run. Each node reads from the context and writes results back
//! into it. The context is scoped to one [`ExecutionId`].

use std::collections::HashMap;
use std::time::Instant;
use zenic_proto::{ExecutionId, NodeId, SessionId, TenantId};

// ---------------------------------------------------------------------------
// NodeInput
// ---------------------------------------------------------------------------

/// Input data for a single node execution.
///
/// Collected from the outputs of all predecessor nodes in the DAG.
#[derive(Debug, Clone)]
pub struct NodeInput {
    /// The node that will receive this input.
    pub target_node_id: NodeId,
    /// Outputs from predecessor nodes, keyed by their NodeId.
    pub predecessor_outputs: HashMap<NodeId, NodeOutput>,
}

impl NodeInput {
    /// Creates an empty input for a node.
    pub fn empty(target_node_id: NodeId) -> Self {
        Self {
            target_node_id,
            predecessor_outputs: HashMap::new(),
        }
    }

    /// Adds a predecessor's output to the input.
    pub fn add_predecessor_output(&mut self, node_id: NodeId, output: NodeOutput) {
        self.predecessor_outputs.insert(node_id, output);
    }

    /// Returns the number of predecessor outputs available.
    pub fn predecessor_count(&self) -> usize {
        self.predecessor_outputs.len()
    }

    /// Returns a specific predecessor's output.
    pub fn get_predecessor_output(&self, node_id: &NodeId) -> Option<&NodeOutput> {
        self.predecessor_outputs.get(node_id)
    }
}

// ---------------------------------------------------------------------------
// NodeOutput
// ---------------------------------------------------------------------------

/// Output data from a single node execution.
///
/// Nodes produce a key-value map of typed data. Downstream nodes
/// read specific keys from their predecessor outputs.
#[derive(Debug, Clone)]
pub struct NodeOutput {
    /// The node that produced this output.
    pub source_node_id: NodeId,
    /// Key-value result pairs.
    pub data: HashMap<String, serde_json::Value>,
    /// Whether the node execution was successful.
    pub success: bool,
    /// Optional error message if `success` is false.
    pub error_message: Option<String>,
}

impl NodeOutput {
    /// Creates a successful output.
    pub fn success(source_node_id: NodeId, data: HashMap<String, serde_json::Value>) -> Self {
        Self {
            source_node_id,
            data,
            success: true,
            error_message: None,
        }
    }

    /// Creates a failed output with an error message.
    pub fn failure(source_node_id: NodeId, error_message: String) -> Self {
        Self {
            source_node_id,
            data: HashMap::new(),
            success: false,
            error_message: Some(error_message),
        }
    }

    /// Creates an empty successful output (no data produced).
    pub fn empty_success(source_node_id: NodeId) -> Self {
        Self::success(source_node_id, HashMap::new())
    }

    /// Retrieves a specific data key from the output.
    pub fn get(&self, key: &str) -> Option<&serde_json::Value> {
        self.data.get(key)
    }
}

// ---------------------------------------------------------------------------
// ExecutionContext
// ---------------------------------------------------------------------------

/// Context for a single DAG execution run.
///
/// Holds all intermediate results and metadata for the duration
/// of one execution. Each node reads inputs from this context
/// and writes outputs back into it.
pub struct ExecutionContext {
    /// Unique execution identifier.
    pub execution_id: ExecutionId,
    /// The session that initiated this execution.
    pub session_id: SessionId,
    /// The tenant that owns this execution.
    pub tenant_id: TenantId,
    /// Outputs produced by nodes that have already executed.
    node_outputs: HashMap<NodeId, NodeOutput>,
    /// When this execution started.
    pub started_at: Instant,
}

impl ExecutionContext {
    /// Creates a new execution context.
    pub fn new(execution_id: ExecutionId, session_id: SessionId, tenant_id: TenantId) -> Self {
        Self {
            execution_id,
            session_id,
            tenant_id,
            node_outputs: HashMap::new(),
            started_at: Instant::now(),
        }
    }

    /// Stores a node's output in the context.
    pub fn store_output(&mut self, output: NodeOutput) {
        self.node_outputs.insert(output.source_node_id, output);
    }

    /// Retrieves a node's output from the context.
    pub fn get_output(&self, node_id: &NodeId) -> Option<&NodeOutput> {
        self.node_outputs.get(node_id)
    }

    /// Returns the number of nodes that have produced output.
    pub fn completed_node_count(&self) -> usize {
        self.node_outputs.len()
    }

    /// Checks whether a specific node has completed.
    pub fn is_node_completed(&self, node_id: &NodeId) -> bool {
        self.node_outputs.contains_key(node_id)
    }

    /// Builds the input for a node by collecting outputs from all predecessors.
    pub fn build_node_input(&self, target_node_id: NodeId, predecessor_ids: &[NodeId]) -> NodeInput {
        let mut input = NodeInput::empty(target_node_id);
        for pred_id in predecessor_ids {
            if let Some(output) = self.node_outputs.get(pred_id) {
                input.add_predecessor_output(*pred_id, output.clone());
            }
        }
        input
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn node_input_empty() {
        let id = NodeId::new();
        let input = NodeInput::empty(id);
        assert_eq!(input.target_node_id, id);
        assert_eq!(input.predecessor_count(), 0);
    }

    #[test]
    fn node_input_add_predecessor() {
        let target = NodeId::new();
        let pred = NodeId::new();
        let mut input = NodeInput::empty(target);
        input.add_predecessor_output(pred, NodeOutput::empty_success(pred));
        assert_eq!(input.predecessor_count(), 1);
        assert!(input.get_predecessor_output(&pred).is_some());
    }

    #[test]
    fn node_output_success() {
        let id = NodeId::new();
        let mut data = HashMap::new();
        data.insert("amount".to_string(), serde_json::json!(1500));
        let output = NodeOutput::success(id, data);
        assert!(output.success);
        assert!(output.error_message.is_none());
        assert_eq!(output.get("amount").unwrap(), &serde_json::json!(1500));
    }

    #[test]
    fn node_output_failure() {
        let id = NodeId::new();
        let output = NodeOutput::failure(id, "connection refused".to_string());
        assert!(!output.success);
        assert_eq!(output.error_message.as_deref(), Some("connection refused"));
        assert!(output.data.is_empty());
    }

    #[test]
    fn node_output_empty_success() {
        let id = NodeId::new();
        let output = NodeOutput::empty_success(id);
        assert!(output.success);
        assert!(output.data.is_empty());
    }

    #[test]
    fn execution_context_store_and_retrieve() {
        let ctx = ExecutionContext::new(
            ExecutionId::new(),
            SessionId::new(),
            TenantId::new(),
        );
        assert_eq!(ctx.completed_node_count(), 0);

        let id = NodeId::new();
        let output = NodeOutput::empty_success(id);
        let mut ctx = ctx;
        ctx.store_output(output);
        assert_eq!(ctx.completed_node_count(), 1);
        assert!(ctx.is_node_completed(&id));
        assert!(ctx.get_output(&id).is_some());
    }

    #[test]
    fn execution_context_build_node_input() {
        let mut ctx = ExecutionContext::new(
            ExecutionId::new(),
            SessionId::new(),
            TenantId::new(),
        );
        let pred1 = NodeId::new();
        let pred2 = NodeId::new();
        let target = NodeId::new();

        ctx.store_output(NodeOutput::empty_success(pred1));
        ctx.store_output(NodeOutput::empty_success(pred2));

        let input = ctx.build_node_input(target, &[pred1, pred2]);
        assert_eq!(input.target_node_id, target);
        assert_eq!(input.predecessor_count(), 2);
    }
}
