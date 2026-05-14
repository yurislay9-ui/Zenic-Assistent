//! Error types for the runtime layer.

use std::time::Duration;
use thiserror::Error;
use zenic_graph::GraphError;
use zenic_proto::{ExecutionId, NodeId, SubGraphId};

/// Errors that can occur during DAG execution.
#[derive(Debug, Error)]
pub enum RuntimeError {
    /// A node execution failed.
    #[error("node execution failed: node {node_id} ({node_name}): {message}")]
    NodeExecutionFailed {
        node_id: NodeId,
        node_name: String,
        message: String,
    },

    /// A node timed out during execution.
    #[error("node execution timeout: node {node_id} ({node_name}) exceeded {timeout:?}")]
    NodeTimeout {
        node_id: NodeId,
        node_name: String,
        timeout: Duration,
    },

    /// Memory budget exceeded.
    #[error("memory budget exceeded: requested {requested} bytes, available {available} bytes")]
    MemoryBudgetExceeded {
        requested: u64,
        available: u64,
    },

    /// Too many nodes loaded in RAM.
    #[error("too many nodes loaded: {current} nodes, maximum is {max}")]
    TooManyNodesLoaded {
        current: usize,
        max: usize,
    },

    /// A required node was not loaded when execution was attempted.
    #[error("node not loaded: {0}")]
    NodeNotLoaded(NodeId),

    /// No executor registered for a node.
    #[error("no executor registered for node {0}")]
    NoExecutorRegistered(NodeId),

    /// Sub-graph loading failed.
    #[error("sub-graph load failed: {sub_graph_id}: {message}")]
    SubGraphLoadFailed {
        sub_graph_id: SubGraphId,
        message: String,
    },

    /// Sub-graph not found on disk.
    #[error("sub-graph not found on disk: {0}")]
    SubGraphNotFound(SubGraphId),

    /// DAG validation error propagated from zenic-graph.
    #[error("graph error: {0}")]
    GraphError(#[from] GraphError),

    /// The execution was cancelled.
    #[error("execution cancelled: {0}")]
    ExecutionCancelled(ExecutionId),

    /// A general runtime error.
    #[error("runtime error: {0}")]
    General(String),
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn node_execution_failed_display() {
        let err = RuntimeError::NodeExecutionFailed {
            node_id: NodeId::new(),
            node_name: "inventory_check".to_string(),
            message: "API connection refused".to_string(),
        };
        let msg = err.to_string();
        assert!(msg.contains("inventory_check"));
        assert!(msg.contains("API connection refused"));
    }

    #[test]
    fn memory_budget_exceeded_display() {
        let err = RuntimeError::MemoryBudgetExceeded {
            requested: 4096,
            available: 1024,
        };
        let msg = err.to_string();
        assert!(msg.contains("4096"));
        assert!(msg.contains("1024"));
    }

    #[test]
    fn too_many_nodes_loaded_display() {
        let err = RuntimeError::TooManyNodesLoaded {
            current: 30,
            max: 25,
        };
        let msg = err.to_string();
        assert!(msg.contains("30"));
        assert!(msg.contains("25"));
    }

    #[test]
    fn no_executor_registered_display() {
        let id = NodeId::new();
        let err = RuntimeError::NoExecutorRegistered(id);
        assert!(err.to_string().contains("no executor"));
    }

    #[test]
    fn from_graph_error() {
        let graph_err = zenic_graph::GraphError::EmptyGraph("test".to_string());
        let runtime_err: RuntimeError = graph_err.into();
        assert!(matches!(runtime_err, RuntimeError::GraphError(_)));
    }
}
