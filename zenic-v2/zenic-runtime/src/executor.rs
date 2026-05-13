//! Node executor trait and registry.
//!
//! The [`NodeExecutor`] trait defines how a node processes input and produces
//! output. The [`NodeExecutorRegistry`] maps [`NodeId`]s to their executors.
//! Nodes without a registered executor cannot run.

use std::collections::HashMap;
use std::time::Instant;
use zenic_proto::NodeId;
use crate::context::{NodeInput, NodeOutput};
use crate::errors::RuntimeError;
use crate::result::NodeResult;

// ---------------------------------------------------------------------------
// NodeExecutor trait
// ---------------------------------------------------------------------------

/// Trait for node execution logic.
///
/// Each node type in the system must implement this trait. The executor
/// receives input from predecessor nodes and produces output for
/// successor nodes.
pub trait NodeExecutor: Send + Sync {
    /// Executes the node logic.
    ///
    /// - `input`: Data from predecessor nodes.
    ///
    /// Returns the output on success, or an error message on failure.
    fn execute(&self, input: &NodeInput) -> Result<NodeOutput, String>;

    /// Returns the human-readable name of this executor (for diagnostics).
    fn name(&self) -> &str;
}

// ---------------------------------------------------------------------------
// NodeExecutorRegistry
// ---------------------------------------------------------------------------

/// Registry that maps [`NodeId`]s to their [`NodeExecutor`] implementations.
///
/// The registry is populated at startup and is immutable during execution.
/// Each node in the DAG must have exactly one executor registered.
pub struct NodeExecutorRegistry {
    executors: HashMap<NodeId, Box<dyn NodeExecutor>>,
}

impl NodeExecutorRegistry {
    /// Creates an empty registry.
    pub fn new() -> Self {
        Self {
            executors: HashMap::new(),
        }
    }

    /// Registers an executor for a node.
    ///
    /// Returns an error if an executor is already registered for the node.
    pub fn register(
        &mut self,
        node_id: NodeId,
        executor: Box<dyn NodeExecutor>,
    ) -> Result<(), RuntimeError> {
        if self.executors.contains_key(&node_id) {
            return Err(RuntimeError::General(format!(
                "executor already registered for node {}",
                node_id
            )));
        }
        self.executors.insert(node_id, executor);
        Ok(())
    }

    /// Returns the executor for a node.
    pub fn get(&self, node_id: &NodeId) -> Option<&dyn NodeExecutor> {
        self.executors.get(node_id).map(|e| e.as_ref())
    }

    /// Returns the number of registered executors.
    pub fn len(&self) -> usize {
        self.executors.len()
    }

    /// Whether the registry is empty.
    pub fn is_empty(&self) -> bool {
        self.executors.is_empty()
    }

    /// Executes a node through its registered executor.
    ///
    /// Returns a [`NodeResult`] with timing information.
    pub fn execute_node(
        &self,
        node_id: &NodeId,
        node_name: &str,
        input: &NodeInput,
        memory_bytes: u64,
    ) -> NodeResult {
        let start = Instant::now();

        let executor = match self.executors.get(node_id) {
            Some(e) => e,
            None => {
                return NodeResult::failed(
                    *node_id,
                    node_name.to_string(),
                    start.elapsed(),
                    format!("no executor registered for node {}", node_id),
                );
            }
        };

        match executor.execute(input) {
            Ok(_output) => NodeResult::completed(
                *node_id,
                node_name.to_string(),
                start.elapsed(),
                memory_bytes,
            ),
            Err(msg) => NodeResult::failed(
                *node_id,
                node_name.to_string(),
                start.elapsed(),
                msg,
            ),
        }
    }
}

impl Default for NodeExecutorRegistry {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Built-in: PassThroughExecutor
// ---------------------------------------------------------------------------

/// A simple executor that passes through its first predecessor's output.
///
/// Useful as a placeholder or for routing nodes that just forward data.
pub struct PassThroughExecutor {
    name: String,
}

impl PassThroughExecutor {
    /// Creates a new pass-through executor.
    pub fn new(name: &str) -> Self {
        Self {
            name: name.to_string(),
        }
    }
}

impl NodeExecutor for PassThroughExecutor {
    fn execute(&self, input: &NodeInput) -> Result<NodeOutput, String> {
        let first_output = input
            .predecessor_outputs
            .values()
            .next()
            .cloned()
            .unwrap_or_else(|| NodeOutput::empty_success(input.target_node_id));
        Ok(first_output)
    }

    fn name(&self) -> &str {
        &self.name
    }
}

// ---------------------------------------------------------------------------
// Built-in: NoOpExecutor
// ---------------------------------------------------------------------------

/// An executor that does nothing and returns an empty success.
///
/// Useful for placeholder or orchestrator nodes that don't produce data.
pub struct NoOpExecutor {
    name: String,
}

impl NoOpExecutor {
    /// Creates a new no-op executor.
    pub fn new(name: &str) -> Self {
        Self {
            name: name.to_string(),
        }
    }
}

impl NodeExecutor for NoOpExecutor {
    fn execute(&self, input: &NodeInput) -> Result<NodeOutput, String> {
        Ok(NodeOutput::empty_success(input.target_node_id))
    }

    fn name(&self) -> &str {
        &self.name
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_register_and_get() {
        let mut reg = NodeExecutorRegistry::new();
        let id = NodeId::new();
        reg.register(id, Box::new(NoOpExecutor::new("test")))
            .expect("register");
        assert_eq!(reg.len(), 1);
        assert!(reg.get(&id).is_some());
    }

    #[test]
    fn registry_duplicate_fails() {
        let mut reg = NodeExecutorRegistry::new();
        let id = NodeId::new();
        reg.register(id, Box::new(NoOpExecutor::new("test")))
            .expect("register");
        let result = reg.register(id, Box::new(NoOpExecutor::new("dup")));
        assert!(result.is_err());
    }

    #[test]
    fn registry_execute_noop() {
        let mut reg = NodeExecutorRegistry::new();
        let id = NodeId::new();
        reg.register(id, Box::new(NoOpExecutor::new("noop")))
            .expect("register");
        let input = NodeInput::empty(id);
        let result = reg.execute_node(&id, "noop", &input, 128);
        assert!(result.is_success());
    }

    #[test]
    fn registry_execute_missing_executor() {
        let reg = NodeExecutorRegistry::new();
        let id = NodeId::new();
        let input = NodeInput::empty(id);
        let result = reg.execute_node(&id, "missing", &input, 0);
        assert!(!result.is_success());
        assert!(result.error_message.is_some());
    }

    #[test]
    fn passthrough_executor() {
        let exec = PassThroughExecutor::new("passthrough");
        let target = NodeId::new();
        let pred = NodeId::new();
        let mut input = NodeInput::empty(target);
        let mut data = HashMap::new();
        data.insert("key".to_string(), serde_json::json!("value"));
        input.add_predecessor_output(pred, NodeOutput::success(pred, data));
        let output = exec.execute(&input).expect("execute");
        assert!(output.success);
        assert_eq!(output.get("key").unwrap(), &serde_json::json!("value"));
    }

    #[test]
    fn noop_executor() {
        let exec = NoOpExecutor::new("noop");
        let target = NodeId::new();
        let input = NodeInput::empty(target);
        let output = exec.execute(&input).expect("execute");
        assert!(output.success);
        assert!(output.data.is_empty());
    }

    #[test]
    fn registry_default_is_new() {
        let reg = NodeExecutorRegistry::default();
        assert!(reg.is_empty());
    }
}
