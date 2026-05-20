//! Workflow instance: runtime state of a running workflow.

use zenic_proto::{ExecutionId, SessionId, TenantId, WorkflowId};

use crate::errors::FlowError;
use crate::status::WorkflowStatus;
use crate::step::StepResult;

/// A running instance of a workflow definition.
///
/// Tracks the current execution state: which step is active,
/// the results of completed steps, and the overall status.
pub struct WorkflowInstance {
    /// The workflow definition ID.
    pub definition_id: WorkflowId,
    /// Unique execution instance ID.
    pub execution_id: ExecutionId,
    /// The session that initiated this workflow.
    pub session_id: SessionId,
    /// The tenant that owns this workflow.
    pub tenant_id: TenantId,
    /// Index of the next step to execute.
    pub current_step_index: usize,
    /// Current workflow status.
    pub status: WorkflowStatus,
    /// Results of executed steps.
    pub step_results: Vec<StepResult>,
    /// When this instance was created (ms since epoch).
    pub started_at_ms: u64,
    /// When this instance reached a terminal state (ms since epoch).
    pub completed_at_ms: Option<u64>,
}

impl WorkflowInstance {
    /// Creates a new workflow instance in Pending state.
    pub fn new(
        definition_id: WorkflowId,
        execution_id: ExecutionId,
        session_id: SessionId,
        tenant_id: TenantId,
        started_at_ms: u64,
    ) -> Self {
        Self {
            definition_id,
            execution_id,
            session_id,
            tenant_id,
            current_step_index: 0,
            status: WorkflowStatus::Pending,
            step_results: Vec::new(),
            started_at_ms,
            completed_at_ms: None,
        }
    }

    /// Transitions the workflow to a new status.
    ///
    /// Validates the transition and returns an error if it is illegal.
    pub fn transition_to(&mut self, new_status: WorkflowStatus) -> Result<(), FlowError> {
        if !self.status.can_transition_to(new_status) {
            return Err(FlowError::InvalidTransition {
                from: self.status,
                to: new_status,
            });
        }
        self.status = new_status;
        if new_status.is_terminal() {
            // BUG FIX: Use the engine's monotonic clock for completed_at_ms
            // instead of started_at_ms. The caller must call transition_to()
            // after updating the engine clock, or provide the actual timestamp.
            // For now, we leave completed_at_ms as None and let the engine
            // set it explicitly via a separate method.
            self.completed_at_ms = None;
        }
        Ok(())
    }

    /// Whether this instance is in a terminal state.
    pub fn is_terminal(&self) -> bool {
        self.status.is_terminal()
    }

    /// Sets the completion timestamp explicitly.
    pub fn set_completed_at(&mut self, timestamp_ms: u64) {
        self.completed_at_ms = Some(timestamp_ms);
    }

    /// Whether this instance completed successfully.
    pub fn is_success(&self) -> bool {
        self.status == WorkflowStatus::Completed
    }

    /// Returns the number of completed steps.
    pub fn completed_step_count(&self) -> usize {
        self.step_results.iter().filter(|r| r.is_success()).count()
    }
}
