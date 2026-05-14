//! Error types for the core (orchestrator) layer.
//!
//! [`CoreError`] is the unified error type that wraps errors from all
//! subsystems: runtime, flow, policy, and graph. The orchestrator
//! returns `CoreError` so that callers receive a single error type
//! regardless of which subsystem failed.

use thiserror::Error;
use zenic_flow::FlowError;
use zenic_graph::GraphError;
use zenic_policy::PolicyError;
use zenic_proto::{ExecutionId, NodeId, SessionId, WorkflowId};
use zenic_runtime::RuntimeError;

// ---------------------------------------------------------------------------
// CoreError
// ---------------------------------------------------------------------------

/// Errors that can occur during orchestration of Zenic-Agents subsystems.
///
/// This enum wraps all subsystem-specific errors into a single type
/// so that callers of the orchestrator do not need to handle multiple
/// error types. Each variant preserves the original error for
/// diagnostic purposes.
#[derive(Debug, Error)]
pub enum CoreError {
    /// A runtime execution error occurred (DAG scheduler, memory, etc.).
    #[error("runtime error: {0}")]
    Runtime(#[from] RuntimeError),

    /// A flow (durable workflow) error occurred.
    #[error("flow error: {0}")]
    Flow(#[from] FlowError),

    /// A policy (access control) error occurred.
    #[error("policy error: {0}")]
    Policy(#[from] PolicyError),

    /// A graph (DAG structure) error occurred.
    #[error("graph error: {0}")]
    Graph(#[from] GraphError),

    /// A session was not found in the active sessions.
    #[error("session not found: {0}")]
    SessionNotFound(SessionId),

    /// A node was not found in the catalog.
    #[error("node not found in catalog: {0}")]
    NodeNotFound(NodeId),

    /// A workflow was not found.
    #[error("workflow not found: {0}")]
    WorkflowNotFound(WorkflowId),

    /// An execution was not found.
    #[error("execution not found: {0}")]
    ExecutionNotFound(ExecutionId),

    /// The orchestrator has not been initialized.
    #[error("orchestrator not initialized")]
    NotInitialized,

    /// The orchestrator is already shut down.
    #[error("orchestrator already shut down")]
    AlreadyShutdown,

    /// A validation error in the core layer.
    #[error("core validation error: {0}")]
    Validation(String),

    /// A general core error.
    #[error("core error: {0}")]
    General(String),
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn runtime_error_wrapping() {
        let rt_err = RuntimeError::General("test runtime error".to_string());
        let core_err: CoreError = rt_err.into();
        let msg = core_err.to_string();
        assert!(msg.contains("runtime error"));
        assert!(msg.contains("test runtime error"));
    }

    #[test]
    fn flow_error_wrapping() {
        let flow_err = FlowError::Validation("bad workflow".to_string());
        let core_err: CoreError = flow_err.into();
        let msg = core_err.to_string();
        assert!(msg.contains("flow error"));
    }

    #[test]
    fn policy_error_wrapping() {
        let policy_err = PolicyError::General("access denied".to_string());
        let core_err: CoreError = policy_err.into();
        let msg = core_err.to_string();
        assert!(msg.contains("policy error"));
    }

    #[test]
    fn graph_error_wrapping() {
        let graph_err = GraphError::EmptyGraph("test".to_string());
        let core_err: CoreError = graph_err.into();
        let msg = core_err.to_string();
        assert!(msg.contains("graph error"));
    }

    #[test]
    fn session_not_found_display() {
        let err = CoreError::SessionNotFound(SessionId::new());
        assert!(err.to_string().contains("session not found"));
    }

    #[test]
    fn node_not_found_display() {
        let err = CoreError::NodeNotFound(NodeId::new());
        assert!(err.to_string().contains("node not found"));
    }

    #[test]
    fn validation_error_display() {
        let err = CoreError::Validation("invalid config".to_string());
        assert!(err.to_string().contains("invalid config"));
    }

    #[test]
    fn general_error_display() {
        let err = CoreError::General("something went wrong".to_string());
        assert!(err.to_string().contains("something went wrong"));
    }
}
