//! Checkpoint data structure for durable workflow persistence.
//!
//! A checkpoint captures the complete state of a running workflow instance
//! at a specific point in time. It is serialized using bincode + zstd
//! (the canonical on-disk format from zenic-proto) and can be used to
//! resume a workflow after a crash or restart.

use serde::{Deserialize, Serialize};
use zenic_proto::{encode, decode, ExecutionId, WorkflowId};

use crate::errors::FlowError;
use crate::status::WorkflowStatus;
use crate::step::StepResult;

// ---------------------------------------------------------------------------
// Checkpoint
// ---------------------------------------------------------------------------

/// A snapshot of a workflow instance's state at a given moment.
///
/// Checkpoints are saved after each successful step execution.
/// If the process crashes, the latest checkpoint can be loaded
/// to resume the workflow from the last completed step.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Checkpoint {
    /// The workflow definition ID.
    pub workflow_id: WorkflowId,
    /// The unique execution instance ID.
    pub execution_id: ExecutionId,
    /// Index of the next step to execute (0 = start from first step).
    pub current_step_index: usize,
    /// Current workflow status at checkpoint time.
    pub workflow_status: WorkflowStatus,
    /// Results of all steps executed so far.
    pub step_results: Vec<StepResult>,
    /// Monotonic timestamp when this checkpoint was created (milliseconds since epoch).
    pub created_at_ms: u64,
}

impl Checkpoint {
    /// Creates a new checkpoint.
    pub fn new(
        workflow_id: WorkflowId,
        execution_id: ExecutionId,
        current_step_index: usize,
        workflow_status: WorkflowStatus,
        step_results: Vec<StepResult>,
        created_at_ms: u64,
    ) -> Self {
        Self {
            workflow_id,
            execution_id,
            current_step_index,
            workflow_status,
            step_results,
            created_at_ms,
        }
    }

    /// Creates an initial checkpoint for a workflow that hasn't started yet.
    pub fn initial(workflow_id: WorkflowId, execution_id: ExecutionId, created_at_ms: u64) -> Self {
        Self {
            workflow_id,
            execution_id,
            current_step_index: 0,
            workflow_status: WorkflowStatus::Pending,
            step_results: Vec::new(),
            created_at_ms,
        }
    }

    /// Serializes this checkpoint to bytes using bincode + zstd.
    pub fn to_bytes(&self) -> Result<Vec<u8>, FlowError> {
        encode(self).map_err(|e| FlowError::SerializationError(e.to_string()))
    }

    /// Deserializes a checkpoint from bytes (bincode + zstd).
    pub fn from_bytes(data: &[u8]) -> Result<Self, FlowError> {
        decode(data).map_err(|e| FlowError::SerializationError(e.to_string()))
    }

    /// Whether this checkpoint represents a workflow that can be resumed.
    pub fn is_resumable(&self) -> bool {
        matches!(
            self.workflow_status,
            WorkflowStatus::Pending | WorkflowStatus::Running
        )
    }

    /// Returns the number of completed steps at checkpoint time.
    pub fn completed_step_count(&self) -> usize {
        self.step_results
            .iter()
            .filter(|r| r.is_success())
            .count()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn checkpoint_initial() {
        let wf_id = WorkflowId::new();
        let exec_id = ExecutionId::new();
        let cp = Checkpoint::initial(wf_id, exec_id, 1000);
        assert_eq!(cp.workflow_id, wf_id);
        assert_eq!(cp.execution_id, exec_id);
        assert_eq!(cp.current_step_index, 0);
        assert_eq!(cp.workflow_status, WorkflowStatus::Pending);
        assert!(cp.step_results.is_empty());
        assert!(cp.is_resumable());
    }

    #[test]
    fn checkpoint_new_with_results() {
        let wf_id = WorkflowId::new();
        let exec_id = ExecutionId::new();
        let results = vec![
            StepResult::completed("step1".to_string(), 0, vec![42], 1, 50),
        ];
        let cp = Checkpoint::new(
            wf_id,
            exec_id,
            1,
            WorkflowStatus::Running,
            results,
            2000,
        );
        assert_eq!(cp.current_step_index, 1);
        assert_eq!(cp.completed_step_count(), 1);
        assert!(cp.is_resumable());
    }

    #[test]
    fn checkpoint_serialization_roundtrip() {
        let wf_id = WorkflowId::new();
        let exec_id = ExecutionId::new();
        let results = vec![
            StepResult::completed("step1".to_string(), 0, vec![1, 2, 3], 1, 10),
            StepResult::completed("step2".to_string(), 1, vec![4, 5, 6], 2, 20),
        ];
        let original = Checkpoint::new(
            wf_id,
            exec_id,
            2,
            WorkflowStatus::Running,
            results,
            3000,
        );

        let bytes = original.to_bytes().expect("encode");
        let restored = Checkpoint::from_bytes(&bytes).expect("decode");

        assert_eq!(original, restored);
    }

    #[test]
    fn checkpoint_not_resumable_when_completed() {
        let cp = Checkpoint::new(
            WorkflowId::new(),
            ExecutionId::new(),
            3,
            WorkflowStatus::Completed,
            vec![],
            5000,
        );
        assert!(!cp.is_resumable());
    }

    #[test]
    fn checkpoint_not_resumable_when_compensated() {
        let cp = Checkpoint::new(
            WorkflowId::new(),
            ExecutionId::new(),
            1,
            WorkflowStatus::Compensated,
            vec![],
            5000,
        );
        assert!(!cp.is_resumable());
    }

    #[test]
    fn checkpoint_completed_step_count() {
        let results = vec![
            StepResult::completed("s1".to_string(), 0, vec![], 1, 10),
            StepResult::failed("s2".to_string(), 1, 3, "error".to_string(), 50),
            StepResult::skipped("s3".to_string(), 2),
        ];
        let cp = Checkpoint::new(
            WorkflowId::new(),
            ExecutionId::new(),
            3,
            WorkflowStatus::Failed,
            results,
            6000,
        );
        assert_eq!(cp.completed_step_count(), 1);
    }

    #[test]
    fn checkpoint_empty_bytes_fails() {
        let result = Checkpoint::from_bytes(&[]);
        assert!(result.is_err());
    }

    #[test]
    fn checkpoint_garbage_bytes_fails() {
        let result = Checkpoint::from_bytes(&[0xDE, 0xAD, 0xBE, 0xEF, 0x00]);
        assert!(result.is_err());
    }
}
