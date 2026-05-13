//! Workflow and step status types for the flow layer.
//!
//! These types define the state machine for durable workflows:
//! - [`WorkflowStatus`] tracks the overall workflow lifecycle.
//! - [`StepStatus`] tracks individual step lifecycle within a workflow.
//!
//! State transitions are validated to prevent illegal state changes.

use serde::{Deserialize, Serialize};
use std::fmt;

// ---------------------------------------------------------------------------
// WorkflowStatus
// ---------------------------------------------------------------------------

/// Status of a durable workflow instance.
///
/// The lifecycle is:
/// `Pending → Running → Completed`
///                   ↘ Failed → Compensating → Compensated
///                   ↘ Cancelled
///
/// A workflow enters `Compensating` when a step fails and SAGA rollback
/// is triggered. After all compensating actions run, it becomes `Compensated`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum WorkflowStatus {
    /// Workflow created but not yet started.
    Pending,
    /// Workflow is executing steps.
    Running,
    /// All steps completed successfully.
    Completed,
    /// A step failed and the workflow cannot continue.
    Failed,
    /// SAGA compensation is in progress (running compensating actions in reverse).
    Compensating,
    /// All compensation actions completed (terminal state).
    Compensated,
    /// Workflow was cancelled by the user or system.
    Cancelled,
}

impl WorkflowStatus {
    /// Returns all valid statuses.
    pub fn all() -> &'static [WorkflowStatus] {
        &[
            Self::Pending,
            Self::Running,
            Self::Completed,
            Self::Failed,
            Self::Compensating,
            Self::Compensated,
            Self::Cancelled,
        ]
    }

    /// Whether this status represents a terminal (non-transitionable) state.
    pub fn is_terminal(self) -> bool {
        matches!(
            self,
            Self::Completed | Self::Compensated | Self::Cancelled
        )
    }

    /// Validates that transitioning from `self` to `next` is legal.
    pub fn can_transition_to(self, next: WorkflowStatus) -> bool {
        match (self, next) {
            // Pending can go to Running or Cancelled.
            (Self::Pending, Self::Running) => true,
            (Self::Pending, Self::Cancelled) => true,

            // Running can go to Completed, Failed, or Cancelled.
            (Self::Running, Self::Completed) => true,
            (Self::Running, Self::Failed) => true,
            (Self::Running, Self::Cancelled) => true,

            // Failed can go to Compensating.
            (Self::Failed, Self::Compensating) => true,

            // Compensating can go to Compensated.
            (Self::Compensating, Self::Compensated) => true,

            // Terminal states cannot transition.
            _ => false,
        }
    }
}

impl fmt::Display for WorkflowStatus {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Pending => write!(f, "pending"),
            Self::Running => write!(f, "running"),
            Self::Completed => write!(f, "completed"),
            Self::Failed => write!(f, "failed"),
            Self::Compensating => write!(f, "compensating"),
            Self::Compensated => write!(f, "compensated"),
            Self::Cancelled => write!(f, "cancelled"),
        }
    }
}

// ---------------------------------------------------------------------------
// StepStatus
// ---------------------------------------------------------------------------

/// Status of a single step within a workflow.
///
/// The lifecycle is:
/// `Pending → Running → Completed`
///                   ↘ Failed
///                   ↘ Skipped
/// `Completed → Compensating → Compensated`
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum StepStatus {
    /// Step has not started yet.
    Pending,
    /// Step is currently executing.
    Running,
    /// Step completed successfully.
    Completed,
    /// Step failed.
    Failed,
    /// Step was skipped (a predecessor failed and skip-on-failure is active).
    Skipped,
    /// SAGA compensation is running for this step.
    Compensating,
    /// Compensation completed for this step.
    Compensated,
}

impl StepStatus {
    /// Whether this step has a successful outcome.
    pub fn is_success(self) -> bool {
        self == Self::Completed
    }

    /// Whether this step is in a terminal state.
    pub fn is_terminal(self) -> bool {
        matches!(
            self,
            Self::Completed | Self::Failed | Self::Skipped | Self::Compensated
        )
    }

    /// Validates that transitioning from `self` to `next` is legal.
    pub fn can_transition_to(self, next: StepStatus) -> bool {
        match (self, next) {
            // Pending can go to Running or Skipped.
            (Self::Pending, Self::Running) => true,
            (Self::Pending, Self::Skipped) => true,

            // Running can go to Completed or Failed.
            (Self::Running, Self::Completed) => true,
            (Self::Running, Self::Failed) => true,

            // Completed can go to Compensating.
            (Self::Completed, Self::Compensating) => true,

            // Compensating can go to Compensated.
            (Self::Compensating, Self::Compensated) => true,

            // Terminal states cannot transition.
            _ => false,
        }
    }
}

impl fmt::Display for StepStatus {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Pending => write!(f, "pending"),
            Self::Running => write!(f, "running"),
            Self::Completed => write!(f, "completed"),
            Self::Failed => write!(f, "failed"),
            Self::Skipped => write!(f, "skipped"),
            Self::Compensating => write!(f, "compensating"),
            Self::Compensated => write!(f, "compensated"),
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // ---- WorkflowStatus tests ----

    #[test]
    fn workflow_status_display() {
        assert_eq!(WorkflowStatus::Pending.to_string(), "pending");
        assert_eq!(WorkflowStatus::Running.to_string(), "running");
        assert_eq!(WorkflowStatus::Completed.to_string(), "completed");
        assert_eq!(WorkflowStatus::Failed.to_string(), "failed");
        assert_eq!(WorkflowStatus::Compensating.to_string(), "compensating");
        assert_eq!(WorkflowStatus::Compensated.to_string(), "compensated");
        assert_eq!(WorkflowStatus::Cancelled.to_string(), "cancelled");
    }

    #[test]
    fn workflow_status_all_count() {
        assert_eq!(WorkflowStatus::all().len(), 7);
    }

    #[test]
    fn workflow_terminal_states() {
        assert!(WorkflowStatus::Completed.is_terminal());
        assert!(WorkflowStatus::Compensated.is_terminal());
        assert!(WorkflowStatus::Cancelled.is_terminal());
        assert!(!WorkflowStatus::Pending.is_terminal());
        assert!(!WorkflowStatus::Running.is_terminal());
        assert!(!WorkflowStatus::Failed.is_terminal());
        assert!(!WorkflowStatus::Compensating.is_terminal());
    }

    #[test]
    fn workflow_valid_transitions() {
        assert!(WorkflowStatus::Pending.can_transition_to(WorkflowStatus::Running));
        assert!(WorkflowStatus::Pending.can_transition_to(WorkflowStatus::Cancelled));
        assert!(WorkflowStatus::Running.can_transition_to(WorkflowStatus::Completed));
        assert!(WorkflowStatus::Running.can_transition_to(WorkflowStatus::Failed));
        assert!(WorkflowStatus::Running.can_transition_to(WorkflowStatus::Cancelled));
        assert!(WorkflowStatus::Failed.can_transition_to(WorkflowStatus::Compensating));
        assert!(WorkflowStatus::Compensating.can_transition_to(WorkflowStatus::Compensated));
    }

    #[test]
    fn workflow_invalid_transitions() {
        assert!(!WorkflowStatus::Completed.can_transition_to(WorkflowStatus::Running));
        assert!(!WorkflowStatus::Compensated.can_transition_to(WorkflowStatus::Running));
        assert!(!WorkflowStatus::Cancelled.can_transition_to(WorkflowStatus::Running));
        assert!(!WorkflowStatus::Pending.can_transition_to(WorkflowStatus::Completed));
        assert!(!WorkflowStatus::Running.can_transition_to(WorkflowStatus::Pending));
    }

    // ---- StepStatus tests ----

    #[test]
    fn step_status_display() {
        assert_eq!(StepStatus::Pending.to_string(), "pending");
        assert_eq!(StepStatus::Compensating.to_string(), "compensating");
    }

    #[test]
    fn step_is_success() {
        assert!(StepStatus::Completed.is_success());
        assert!(!StepStatus::Failed.is_success());
        assert!(!StepStatus::Skipped.is_success());
    }

    #[test]
    fn step_terminal_states() {
        assert!(StepStatus::Completed.is_terminal());
        assert!(StepStatus::Failed.is_terminal());
        assert!(StepStatus::Skipped.is_terminal());
        assert!(StepStatus::Compensated.is_terminal());
        assert!(!StepStatus::Pending.is_terminal());
        assert!(!StepStatus::Running.is_terminal());
        assert!(!StepStatus::Compensating.is_terminal());
    }

    #[test]
    fn step_valid_transitions() {
        assert!(StepStatus::Pending.can_transition_to(StepStatus::Running));
        assert!(StepStatus::Pending.can_transition_to(StepStatus::Skipped));
        assert!(StepStatus::Running.can_transition_to(StepStatus::Completed));
        assert!(StepStatus::Running.can_transition_to(StepStatus::Failed));
        assert!(StepStatus::Completed.can_transition_to(StepStatus::Compensating));
        assert!(StepStatus::Compensating.can_transition_to(StepStatus::Compensated));
    }

    #[test]
    fn step_invalid_transitions() {
        assert!(!StepStatus::Failed.can_transition_to(StepStatus::Running));
        assert!(!StepStatus::Completed.can_transition_to(StepStatus::Running));
        assert!(!StepStatus::Compensated.can_transition_to(StepStatus::Compensating));
    }
}
