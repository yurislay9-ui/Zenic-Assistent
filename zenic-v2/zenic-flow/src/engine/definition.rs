//! Workflow definition: the blueprint for a durable workflow.

use std::collections::HashMap;

use zenic_proto::WorkflowId;

use crate::errors::FlowError;
use crate::retry::RetryPolicy;
use crate::step::WorkflowStep;

/// Definition of a durable workflow (the blueprint).
///
/// Contains the ordered list of steps, default retry policy,
/// and metadata. Workflow definitions are immutable once created.
#[derive(Debug, Clone)]
pub struct WorkflowDefinition {
    /// Unique identifier for this workflow definition.
    pub id: WorkflowId,
    /// Human-readable name.
    pub name: String,
    /// Short description of what this workflow does.
    pub description: String,
    /// Ordered list of steps to execute.
    pub steps: Vec<WorkflowStep>,
    /// Default retry policy applied to steps without an override.
    pub default_retry_policy: RetryPolicy,
}

impl WorkflowDefinition {
    /// Creates a new workflow definition.
    pub fn new(
        id: WorkflowId,
        name: &str,
        description: &str,
        steps: Vec<WorkflowStep>,
        default_retry_policy: RetryPolicy,
    ) -> Self {
        Self {
            id,
            name: name.to_string(),
            description: description.to_string(),
            steps,
            default_retry_policy,
        }
    }

    /// Validates the workflow definition for internal consistency.
    pub fn validate(&self) -> Result<(), FlowError> {
        if self.name.is_empty() {
            return Err(FlowError::Validation(
                "workflow name must not be empty".to_string(),
            ));
        }
        if self.steps.is_empty() {
            return Err(FlowError::Validation(format!(
                "workflow '{}' has no steps",
                self.name
            )));
        }

        // Validate each step.
        for (i, step) in self.steps.iter().enumerate() {
            if let Err(e) = step.validate() {
                return Err(FlowError::Validation(format!(
                    "step {} in workflow '{}': {}",
                    i, self.name, e
                )));
            }
        }

        // Check step names are unique.
        let mut names = HashMap::new();
        for (i, step) in self.steps.iter().enumerate() {
            if let Some(prev) = names.insert(&step.name, i) {
                return Err(FlowError::Validation(format!(
                    "duplicate step name '{}' at indices {} and {} in workflow '{}'",
                    step.name, prev, i, self.name
                )));
            }
        }

        // Validate default retry policy.
        if let Err(e) = self.default_retry_policy.validate() {
            return Err(FlowError::Validation(format!(
                "default retry policy in workflow '{}': {}",
                self.name, e
            )));
        }

        Ok(())
    }

    /// Returns the effective retry policy for a step.
    ///
    /// If the step has its own retry policy, it overrides the default.
    pub fn retry_policy_for_step(&self, step_index: usize) -> RetryPolicy {
        self.steps
            .get(step_index)
            .and_then(|s| s.retry_policy.clone())
            .unwrap_or_else(|| self.default_retry_policy.clone())
    }

    /// Returns the number of steps in this workflow.
    pub fn step_count(&self) -> usize {
        self.steps.len()
    }
}
