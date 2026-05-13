//! Error types for the flow (durable workflow) layer.

use thiserror::Error;
use zenic_proto::{ExecutionId, WorkflowId};

use crate::status::{StepStatus, WorkflowStatus};

/// Errors that can occur during workflow execution.
#[derive(Debug, Error)]
pub enum FlowError {
    /// A workflow was not found.
    #[error("workflow not found: {0}")]
    WorkflowNotFound(WorkflowId),

    /// A workflow step failed after exhausting all retries.
    #[error("step failed at index {step_index} after {attempts} attempts: {message}")]
    StepFailed {
        step_index: usize,
        attempts: u32,
        message: String,
    },

    /// A step timed out during execution.
    #[error("step timeout at index {step_index}")]
    StepTimeout {
        step_index: usize,
    },

    /// Checkpoint save or load failed.
    #[error("checkpoint failed: {0}")]
    CheckpointFailed(String),

    /// A compensation action failed during SAGA rollback.
    #[error("compensation failed at step index {step_index}: {message}")]
    CompensationFailed {
        step_index: usize,
        message: String,
    },

    /// An invalid state transition was attempted.
    #[error("invalid state transition: cannot go from {from} to {to}")]
    InvalidTransition {
        from: WorkflowStatus,
        to: WorkflowStatus,
    },

    /// An invalid step state transition was attempted.
    #[error("invalid step state transition at index {step_index}: cannot go from {from} to {to}")]
    InvalidStepTransition {
        step_index: usize,
        from: StepStatus,
        to: StepStatus,
    },

    /// Maximum retries exceeded for a step.
    #[error("max retries exceeded at step index {step_index}: {attempts} attempts")]
    MaxRetriesExceeded {
        step_index: usize,
        attempts: u32,
    },

    /// A workflow is already running and cannot be started again.
    #[error("workflow already running: {0}")]
    WorkflowAlreadyRunning(WorkflowId),

    /// A workflow was cancelled.
    #[error("workflow cancelled: {0}")]
    WorkflowCancelled(ExecutionId),

    /// Serialization or deserialization failed.
    #[error("serialization error: {0}")]
    SerializationError(String),

    /// Workflow definition validation failed.
    #[error("workflow validation error: {0}")]
    Validation(String),

    /// A general flow error.
    #[error("flow error: {0}")]
    General(String),
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn workflow_not_found_display() {
        let id = WorkflowId::new();
        let err = FlowError::WorkflowNotFound(id);
        let msg = err.to_string();
        assert!(msg.contains("workflow not found"));
    }

    #[test]
    fn step_failed_display() {
        let err = FlowError::StepFailed {
            step_index: 2,
            attempts: 3,
            message: "connection refused".to_string(),
        };
        let msg = err.to_string();
        assert!(msg.contains("step failed"));
        assert!(msg.contains("connection refused"));
        assert!(msg.contains("3 attempts"));
    }

    #[test]
    fn invalid_transition_display() {
        let err = FlowError::InvalidTransition {
            from: WorkflowStatus::Completed,
            to: WorkflowStatus::Running,
        };
        let msg = err.to_string();
        assert!(msg.contains("invalid state transition"));
        assert!(msg.contains("completed"));
        assert!(msg.contains("running"));
    }

    #[test]
    fn compensation_failed_display() {
        let err = FlowError::CompensationFailed {
            step_index: 1,
            message: "rollback API error".to_string(),
        };
        let msg = err.to_string();
        assert!(msg.contains("compensation failed"));
        assert!(msg.contains("rollback API error"));
    }

    #[test]
    fn max_retries_exceeded_display() {
        let err = FlowError::MaxRetriesExceeded {
            step_index: 0,
            attempts: 5,
        };
        let msg = err.to_string();
        assert!(msg.contains("max retries exceeded"));
        assert!(msg.contains("5 attempts"));
    }

    #[test]
    fn serialization_error_display() {
        let err = FlowError::SerializationError("bincode failed".to_string());
        assert!(err.to_string().contains("bincode failed"));
    }

    #[test]
    fn validation_error_display() {
        let err = FlowError::Validation("empty step name".to_string());
        assert!(err.to_string().contains("empty step name"));
    }
}
