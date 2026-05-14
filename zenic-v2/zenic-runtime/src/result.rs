//! Execution result types for DAG runs.
//!
//! These types capture the outcome of a full DAG execution and of
//! individual node executions within that run.

use std::collections::HashMap;
use std::time::Duration;
use zenic_proto::{ExecutionId, NodeId};

// ---------------------------------------------------------------------------
// ExecutionStatus
// ---------------------------------------------------------------------------

/// Status of a DAG execution or a node execution.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum ExecutionStatus {
    /// Execution has not started yet.
    Pending,
    /// Execution is currently in progress.
    Running,
    /// Execution completed successfully.
    Completed,
    /// Execution failed with an error.
    Failed,
    /// Execution was skipped (predecessor failed or condition not met).
    Skipped,
}

impl std::fmt::Display for ExecutionStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Pending => write!(f, "pending"),
            Self::Running => write!(f, "running"),
            Self::Completed => write!(f, "completed"),
            Self::Failed => write!(f, "failed"),
            Self::Skipped => write!(f, "skipped"),
        }
    }
}

// ---------------------------------------------------------------------------
// NodeResult
// ---------------------------------------------------------------------------

/// Result of a single node execution within a DAG run.
#[derive(Debug, Clone)]
pub struct NodeResult {
    /// The node that was executed.
    pub node_id: NodeId,
    /// Human-readable name of the node.
    pub node_name: String,
    /// Execution status.
    pub status: ExecutionStatus,
    /// Wall-clock duration of the node execution.
    pub duration: Duration,
    /// Error message if the node failed.
    pub error_message: Option<String>,
    /// Number of bytes of memory used during execution.
    pub memory_used_bytes: u64,
}

impl NodeResult {
    /// Creates a successful node result.
    pub fn completed(node_id: NodeId, node_name: String, duration: Duration, memory_used_bytes: u64) -> Self {
        Self {
            node_id,
            node_name,
            status: ExecutionStatus::Completed,
            duration,
            error_message: None,
            memory_used_bytes,
        }
    }

    /// Creates a failed node result.
    pub fn failed(node_id: NodeId, node_name: String, duration: Duration, error_message: String) -> Self {
        Self {
            node_id,
            node_name,
            status: ExecutionStatus::Failed,
            duration,
            error_message: Some(error_message),
            memory_used_bytes: 0,
        }
    }

    /// Creates a skipped node result.
    pub fn skipped(node_id: NodeId, node_name: String) -> Self {
        Self {
            node_id,
            node_name,
            status: ExecutionStatus::Skipped,
            duration: Duration::ZERO,
            error_message: None,
            memory_used_bytes: 0,
        }
    }

    /// Whether this result represents a successful execution.
    pub fn is_success(&self) -> bool {
        self.status == ExecutionStatus::Completed
    }
}

// ---------------------------------------------------------------------------
// ExecutionResult
// ---------------------------------------------------------------------------

/// Result of a full DAG execution run.
#[derive(Debug)]
pub struct ExecutionResult {
    /// The execution identifier.
    pub execution_id: ExecutionId,
    /// Overall status of the execution.
    pub status: ExecutionStatus,
    /// Results for each individual node.
    pub node_results: HashMap<NodeId, NodeResult>,
    /// Total wall-clock duration of the execution.
    pub total_duration: Duration,
    /// Peak memory usage during execution (bytes).
    pub peak_memory_bytes: u64,
    /// Number of nodes that completed successfully.
    pub nodes_completed: usize,
    /// Number of nodes that failed.
    pub nodes_failed: usize,
    /// Number of nodes that were skipped.
    pub nodes_skipped: usize,
}

impl ExecutionResult {
    /// Creates a new execution result builder.
    pub fn new(execution_id: ExecutionId) -> Self {
        Self {
            execution_id,
            status: ExecutionStatus::Pending,
            node_results: HashMap::new(),
            total_duration: Duration::ZERO,
            peak_memory_bytes: 0,
            nodes_completed: 0,
            nodes_failed: 0,
            nodes_skipped: 0,
        }
    }

    /// Adds a node result and updates aggregate counters.
    pub fn add_node_result(&mut self, result: NodeResult) {
        match result.status {
            ExecutionStatus::Completed => self.nodes_completed += 1,
            ExecutionStatus::Failed => self.nodes_failed += 1,
            ExecutionStatus::Skipped => self.nodes_skipped += 1,
            ExecutionStatus::Pending | ExecutionStatus::Running => {}
        }
        self.node_results.insert(result.node_id, result);
    }

    /// Finalizes the execution result by setting the overall status.
    ///
    /// - If any node failed, the overall status is `Failed`.
    /// - If all nodes completed or were skipped, the overall status is `Completed`.
    pub fn finalize(&mut self, total_duration: Duration, peak_memory_bytes: u64) {
        self.total_duration = total_duration;
        self.peak_memory_bytes = peak_memory_bytes;
        self.status = if self.nodes_failed > 0 {
            ExecutionStatus::Failed
        } else {
            ExecutionStatus::Completed
        };
    }

    /// Returns the node result for a specific node.
    pub fn get_node_result(&self, node_id: &NodeId) -> Option<&NodeResult> {
        self.node_results.get(node_id)
    }

    /// Whether the entire execution was successful.
    pub fn is_success(&self) -> bool {
        self.status == ExecutionStatus::Completed
    }

    /// Total number of nodes processed (completed + failed + skipped).
    pub fn total_nodes_processed(&self) -> usize {
        self.nodes_completed + self.nodes_failed + self.nodes_skipped
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn execution_status_display() {
        assert_eq!(ExecutionStatus::Pending.to_string(), "pending");
        assert_eq!(ExecutionStatus::Running.to_string(), "running");
        assert_eq!(ExecutionStatus::Completed.to_string(), "completed");
        assert_eq!(ExecutionStatus::Failed.to_string(), "failed");
        assert_eq!(ExecutionStatus::Skipped.to_string(), "skipped");
    }

    #[test]
    fn node_result_completed() {
        let id = NodeId::new();
        let result = NodeResult::completed(id, "test_node".to_string(), Duration::from_millis(50), 1024);
        assert!(result.is_success());
        assert_eq!(result.status, ExecutionStatus::Completed);
        assert_eq!(result.memory_used_bytes, 1024);
        assert!(result.error_message.is_none());
    }

    #[test]
    fn node_result_failed() {
        let id = NodeId::new();
        let result = NodeResult::failed(id, "bad_node".to_string(), Duration::from_millis(10), "timeout".to_string());
        assert!(!result.is_success());
        assert_eq!(result.status, ExecutionStatus::Failed);
        assert_eq!(result.error_message.as_deref(), Some("timeout"));
    }

    #[test]
    fn node_result_skipped() {
        let id = NodeId::new();
        let result = NodeResult::skipped(id, "cond_node".to_string());
        assert!(!result.is_success());
        assert_eq!(result.status, ExecutionStatus::Skipped);
        assert_eq!(result.duration, Duration::ZERO);
    }

    #[test]
    fn execution_result_finalize_all_completed() {
        let exec_id = ExecutionId::new();
        let mut result = ExecutionResult::new(exec_id);
        let n1 = NodeId::new();
        let n2 = NodeId::new();
        result.add_node_result(NodeResult::completed(n1, "a".to_string(), Duration::from_millis(10), 512));
        result.add_node_result(NodeResult::completed(n2, "b".to_string(), Duration::from_millis(20), 1024));
        result.finalize(Duration::from_millis(30), 1536);
        assert!(result.is_success());
        assert_eq!(result.nodes_completed, 2);
        assert_eq!(result.nodes_failed, 0);
        assert_eq!(result.total_nodes_processed(), 2);
    }

    #[test]
    fn execution_result_finalize_with_failure() {
        let exec_id = ExecutionId::new();
        let mut result = ExecutionResult::new(exec_id);
        let n1 = NodeId::new();
        let n2 = NodeId::new();
        result.add_node_result(NodeResult::completed(n1, "a".to_string(), Duration::from_millis(10), 512));
        result.add_node_result(NodeResult::failed(n2, "b".to_string(), Duration::from_millis(5), "error".to_string()));
        result.finalize(Duration::from_millis(15), 512);
        assert!(!result.is_success());
        assert_eq!(result.nodes_completed, 1);
        assert_eq!(result.nodes_failed, 1);
    }

    #[test]
    fn execution_result_get_node_result() {
        let exec_id = ExecutionId::new();
        let mut result = ExecutionResult::new(exec_id);
        let n1 = NodeId::new();
        result.add_node_result(NodeResult::completed(n1, "a".to_string(), Duration::from_millis(10), 256));
        let retrieved = result.get_node_result(&n1);
        assert!(retrieved.is_some());
        assert_eq!(retrieved.unwrap().node_name, "a");
    }
}
