//! Workflow step definition and result types.
//!
//! A [`WorkflowStep`] defines a single step in a durable workflow.
//! A [`StepResult`] captures the outcome of executing a step, including
//! retry counts and error information.

use serde::{Deserialize, Serialize};
use zenic_proto::SubGraphId;

use crate::retry::RetryPolicy;
use crate::status::StepStatus;

// ---------------------------------------------------------------------------
// WorkflowStep
// ---------------------------------------------------------------------------

/// Definition of a single step in a durable workflow.
///
/// Each step corresponds to an atomic unit of work that can be retried
/// and compensated. Steps are executed sequentially within a workflow.
/// The step may reference a specific subgraph for the executor to run.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WorkflowStep {
    /// Canonical name of this step (must be unique within the workflow).
    pub name: String,
    /// Short description of what this step does.
    pub description: String,
    /// Optional reference to the sub-graph this step executes.
    /// The StepExecutor implementation uses this to determine
    /// which DAG or subgraph to run.
    pub sub_graph_id: Option<SubGraphId>,
    /// Step-level retry policy override.
    /// If `None`, the workflow's default retry policy is used.
    pub retry_policy: Option<RetryPolicy>,
    /// Optional key to look up a compensation action in the registry.
    /// If `None`, this step has no compensating action.
    pub compensation_key: Option<String>,
}

impl WorkflowStep {
    /// Creates a simple step with a name and description.
    pub fn new(name: &str, description: &str) -> Self {
        Self {
            name: name.to_string(),
            description: description.to_string(),
            sub_graph_id: None,
            retry_policy: None,
            compensation_key: None,
        }
    }

    /// Creates a step with a sub-graph reference.
    pub fn with_sub_graph(name: &str, description: &str, sub_graph_id: SubGraphId) -> Self {
        Self {
            name: name.to_string(),
            description: description.to_string(),
            sub_graph_id: Some(sub_graph_id),
            retry_policy: None,
            compensation_key: None,
        }
    }

    /// Sets the step-level retry policy.
    pub fn retry_policy(mut self, policy: RetryPolicy) -> Self {
        self.retry_policy = Some(policy);
        self
    }

    /// Sets the compensation key for SAGA rollback.
    pub fn compensation_key(mut self, key: &str) -> Self {
        self.compensation_key = Some(key.to_string());
        self
    }

    /// Validates the step for internal consistency.
    pub fn validate(&self) -> Result<(), String> {
        if self.name.is_empty() {
            return Err("step has empty name".to_string());
        }
        if self.name.contains(' ') {
            return Err(format!(
                "step name '{}' contains spaces (use snake_case)",
                self.name
            ));
        }
        if let Some(policy) = &self.retry_policy {
            policy.validate()?;
        }
        if let Some(key) = &self.compensation_key {
            if key.is_empty() {
                return Err("compensation_key must not be empty if present".to_string());
            }
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// StepResult
// ---------------------------------------------------------------------------

/// Result of executing a single workflow step.
///
/// Captures the outcome, number of attempts, and any error information.
/// This is stored in checkpoints for durability.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StepResult {
    /// Name of the step this result belongs to.
    pub step_name: String,
    /// Index of this step in the workflow's step list.
    pub step_index: usize,
    /// Execution status of this step.
    pub status: StepStatus,
    /// Output data produced by the step (opaque bytes).
    /// This can be passed as input to the next step.
    pub output_data: Option<Vec<u8>>,
    /// Number of attempts made (including the initial attempt and all retries).
    pub attempts: u32,
    /// Error message from the last failed attempt.
    pub last_error: Option<String>,
    /// Wall-clock duration of the last attempt in milliseconds.
    pub duration_ms: u64,
}

impl StepResult {
    /// Creates a successful step result.
    pub fn completed(step_name: String, step_index: usize, output_data: Vec<u8>, attempts: u32, duration_ms: u64) -> Self {
        Self {
            step_name,
            step_index,
            status: StepStatus::Completed,
            output_data: Some(output_data),
            attempts,
            last_error: None,
            duration_ms,
        }
    }

    /// Creates a failed step result.
    pub fn failed(step_name: String, step_index: usize, attempts: u32, error: String, duration_ms: u64) -> Self {
        Self {
            step_name,
            step_index,
            status: StepStatus::Failed,
            output_data: None,
            attempts,
            last_error: Some(error),
            duration_ms,
        }
    }

    /// Creates a skipped step result.
    pub fn skipped(step_name: String, step_index: usize) -> Self {
        Self {
            step_name,
            step_index,
            status: StepStatus::Skipped,
            output_data: None,
            attempts: 0,
            last_error: None,
            duration_ms: 0,
        }
    }

    /// Creates a compensated step result.
    pub fn compensated(step_name: String, step_index: usize) -> Self {
        Self {
            step_name,
            step_index,
            status: StepStatus::Compensated,
            output_data: None,
            attempts: 0,
            last_error: None,
            duration_ms: 0,
        }
    }

    /// Whether this step completed successfully.
    pub fn is_success(&self) -> bool {
        self.status.is_success()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn step_new() {
        let step = WorkflowStep::new("check_inventory", "Check stock levels");
        assert_eq!(step.name, "check_inventory");
        assert!(step.sub_graph_id.is_none());
        assert!(step.retry_policy.is_none());
        assert!(step.compensation_key.is_none());
    }

    #[test]
    fn step_with_sub_graph() {
        let sg_id = SubGraphId::new();
        let step = WorkflowStep::with_sub_graph("check_inventory", "Check stock", sg_id);
        assert_eq!(step.sub_graph_id, Some(sg_id));
    }

    #[test]
    fn step_builder_pattern() {
        let step = WorkflowStep::new("process_order", "Process the order")
            .retry_policy(RetryPolicy::no_retry())
            .compensation_key("cancel_order");
        assert!(step.retry_policy.is_some());
        assert_eq!(step.compensation_key.as_deref(), Some("cancel_order"));
    }

    #[test]
    fn step_validate_valid() {
        let step = WorkflowStep::new("valid_step", "A valid step");
        assert!(step.validate().is_ok());
    }

    #[test]
    fn step_validate_empty_name() {
        let step = WorkflowStep {
            name: String::new(),
            description: "No name".to_string(),
            sub_graph_id: None,
            retry_policy: None,
            compensation_key: None,
        };
        assert!(step.validate().is_err());
    }

    #[test]
    fn step_validate_space_in_name() {
        let step = WorkflowStep {
            name: "has space".to_string(),
            description: "Bad name".to_string(),
            sub_graph_id: None,
            retry_policy: None,
            compensation_key: None,
        };
        assert!(step.validate().is_err());
    }

    #[test]
    fn step_validate_empty_compensation_key() {
        let step = WorkflowStep {
            name: "step".to_string(),
            description: "Test".to_string(),
            sub_graph_id: None,
            retry_policy: None,
            compensation_key: Some(String::new()),
        };
        assert!(step.validate().is_err());
    }

    #[test]
    fn step_result_completed() {
        let result = StepResult::completed(
            "step1".to_string(),
            0,
            vec![1, 2, 3],
            1,
            50,
        );
        assert!(result.is_success());
        assert_eq!(result.status, StepStatus::Completed);
        assert_eq!(result.output_data.as_deref(), Some(&[1, 2, 3][..]));
        assert_eq!(result.attempts, 1);
    }

    #[test]
    fn step_result_failed() {
        let result = StepResult::failed(
            "step2".to_string(),
            1,
            3,
            "connection refused".to_string(),
            100,
        );
        assert!(!result.is_success());
        assert_eq!(result.status, StepStatus::Failed);
        assert_eq!(result.last_error.as_deref(), Some("connection refused"));
        assert_eq!(result.attempts, 3);
    }

    #[test]
    fn step_result_skipped() {
        let result = StepResult::skipped("step3".to_string(), 2);
        assert!(!result.is_success());
        assert_eq!(result.status, StepStatus::Skipped);
        assert_eq!(result.attempts, 0);
        assert_eq!(result.duration_ms, 0);
    }

    #[test]
    fn step_result_compensated() {
        let result = StepResult::compensated("step1".to_string(), 0);
        assert_eq!(result.status, StepStatus::Compensated);
    }
}
