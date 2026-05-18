//! Workflow engine: orchestrates durable workflow execution with
//! checkpoints, SAGA compensation, and retry with exponential backoff.
//!
//! The [`WorkflowEngine`] is the main entry point for executing durable
//! workflows. It coordinates:
//! - Sequential step execution through the [`StepExecutor`](super::StepExecutor) trait
//! - Checkpoint persistence after each step
//! - Retry with configurable backoff policies
//! - SAGA compensation on unrecoverable failure
//!
//! The engine does NOT depend on `zenic-runtime` directly. The
//! [`StepExecutor`](super::StepExecutor) trait abstracts step execution so that `zenic-core`
//! can provide an implementation backed by the runtime's DagScheduler.

use zenic_proto::{ExecutionId, SessionId, TenantId};

use crate::checkpoint::Checkpoint;
use crate::compensation::{CompensationAction, CompensationRegistry};
use crate::errors::FlowError;
use crate::status::{StepStatus, WorkflowStatus};
use crate::step::{StepResult, WorkflowStep};
use crate::retry::RetryPolicy;

use super::definition::WorkflowDefinition;
use super::executor::StepExecutor;
use super::instance::WorkflowInstance;
use super::store::CheckpointStore;

/// Orchestrates durable workflow execution.
///
/// The engine:
/// 1. Validates the workflow definition.
/// 2. Creates a workflow instance.
/// 3. Executes steps sequentially through the StepExecutor.
/// 4. Applies retry policies on failure.
/// 5. Saves checkpoints after each step.
/// 6. Triggers SAGA compensation on unrecoverable failure.
pub struct WorkflowEngine {
    /// Compensation action registry.
    compensation_registry: CompensationRegistry,
    /// Checkpoint persistence store.
    checkpoint_store: CheckpointStore,
    /// Monotonic clock for timestamps (milliseconds).
    clock_ms: u64,
}

impl WorkflowEngine {
    /// Creates a new workflow engine.
    pub fn new() -> Self {
        Self {
            compensation_registry: CompensationRegistry::new(),
            checkpoint_store: CheckpointStore::new(),
            clock_ms: 0,
        }
    }

    // -----------------------------------------------------------------------
    // Compensation registration
    // -----------------------------------------------------------------------

    /// Registers a compensating action for a key.
    pub fn register_compensation(
        &mut self,
        key: &str,
        action: Box<dyn CompensationAction>,
    ) -> Result<(), FlowError> {
        self.compensation_registry.register(key, action)
    }

    // -----------------------------------------------------------------------
    // Checkpoint queries
    // -----------------------------------------------------------------------

    /// Returns the latest checkpoint for an execution.
    pub fn get_checkpoint(&self, execution_id: &ExecutionId) -> Option<Checkpoint> {
        self.checkpoint_store.load(execution_id)
    }

    /// Returns the number of stored checkpoints.
    pub fn checkpoint_count(&self) -> usize {
        self.checkpoint_store.len()
    }

    // -----------------------------------------------------------------------
    // Execution
    // -----------------------------------------------------------------------

    /// Executes a workflow definition to completion.
    ///
    /// This is the primary entry point. It creates a new workflow instance,
    /// validates the definition, and runs all steps sequentially. On failure,
    /// it applies the retry policy. If all retries are exhausted, it triggers
    /// SAGA compensation.
    ///
    /// # Arguments
    ///
    /// - `definition`: The workflow definition to execute.
    /// - `executor`: The step executor implementation.
    /// - `session_id`: The session initiating the workflow.
    /// - `tenant_id`: The tenant owning the workflow.
    pub fn execute(
        &mut self,
        definition: &WorkflowDefinition,
        executor: &dyn StepExecutor,
        session_id: SessionId,
        tenant_id: TenantId,
    ) -> Result<WorkflowInstance, FlowError> {
        // Validate definition.
        definition.validate()?;

        let execution_id = ExecutionId::new();
        let mut instance = WorkflowInstance::new(
            definition.id,
            execution_id,
            session_id,
            tenant_id,
            self.next_timestamp(),
        );

        // Transition to Running.
        instance.transition_to(WorkflowStatus::Running)?;

        // Save initial checkpoint.
        self.save_checkpoint(&instance)?;

        // Execute steps sequentially.
        for step_index in 0..definition.steps.len() {
            instance.current_step_index = step_index;

            let step = &definition.steps[step_index];
            let retry_policy = definition.retry_policy_for_step(step_index);

            // Get input from previous step's output.
            // BUG FIX: Use the LAST successful step's output, not the FIRST.
            // Previously used .iter().find() which returned the first match,
            // causing step 4 to receive input from step 1 instead of step 3.
            let input = instance
                .step_results
                .iter()
                .rev()
                .find(|r| r.is_success())
                .and_then(|r| r.output_data.as_ref())
                .map(|d| d.as_slice());

            // Execute with retries.
            let result = self.execute_step_with_retry(
                step,
                step_index,
                input,
                &retry_policy,
                executor,
            );

            match result {
                Ok((output, attempts)) => {
                    let step_result = StepResult::completed(
                        step.name.clone(),
                        step_index,
                        output,
                        attempts,
                        0, // Duration not tracked in this deterministic engine.
                    );
                    instance.step_results.push(step_result);
                    self.save_checkpoint(&instance)?;
                }
                Err(step_result) => {
                    instance.step_results.push(step_result);

                    // Step failed after all retries. Trigger compensation.
                    instance.transition_to(WorkflowStatus::Failed)?;
                    instance.set_completed_at(self.next_timestamp());
                    self.save_checkpoint(&instance)?;

                    self.run_compensation(&mut instance, definition);

                    return Ok(instance);
                }
            }
        }

        // All steps completed.
        instance.transition_to(WorkflowStatus::Completed)?;
        instance.set_completed_at(self.next_timestamp());
        self.save_checkpoint(&instance)?;

        Ok(instance)
    }

    /// Resumes a workflow from a checkpoint.
    ///
    /// The workflow continues from the step indicated by the checkpoint,
    /// skipping already-completed steps.
    pub fn resume_from_checkpoint(
        &mut self,
        checkpoint: Checkpoint,
        definition: &WorkflowDefinition,
        executor: &dyn StepExecutor,
    ) -> Result<WorkflowInstance, FlowError> {
        if !checkpoint.is_resumable() {
            return Err(FlowError::CheckpointFailed(format!(
                "checkpoint for execution {} is not resumable (status: {})",
                checkpoint.execution_id, checkpoint.workflow_status
            )));
        }

        let mut instance = WorkflowInstance::new(
            checkpoint.workflow_id,
            checkpoint.execution_id,
            SessionId::new(), // New session for resume.
            TenantId::new(),  // Same tenant assumed.
            self.next_timestamp(),
        );

        instance.current_step_index = checkpoint.current_step_index;
        instance.step_results = checkpoint.step_results;

        // Transition to Running.
        instance.transition_to(WorkflowStatus::Running)?;

        // Execute remaining steps.
        for step_index in checkpoint.current_step_index..definition.steps.len() {
            instance.current_step_index = step_index;

            let step = &definition.steps[step_index];
            let retry_policy = definition.retry_policy_for_step(step_index);

            let input = instance
                .step_results
                .last()
                .and_then(|r| r.output_data.as_ref())
                .map(|d| d.as_slice());

            let result = self.execute_step_with_retry(
                step,
                step_index,
                input,
                &retry_policy,
                executor,
            );

            match result {
                Ok((output, attempts)) => {
                    let step_result = StepResult::completed(
                        step.name.clone(),
                        step_index,
                        output,
                        attempts,
                        0,
                    );
                    instance.step_results.push(step_result);
                    self.save_checkpoint(&instance)?;
                }
                Err(step_result) => {
                    instance.step_results.push(step_result);
                    instance.transition_to(WorkflowStatus::Failed)?;
                    self.save_checkpoint(&instance)?;
                    self.run_compensation(&mut instance, definition);
                    return Ok(instance);
                }
            }
        }

        instance.transition_to(WorkflowStatus::Completed)?;
        self.save_checkpoint(&instance)?;

        Ok(instance)
    }

    // -----------------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------------

    /// Executes a step with retry according to the policy.
    ///
    /// Returns `Ok((output, attempt_count))` on success, or `Err(StepResult)`
    /// on failure after all retries are exhausted.
    fn execute_step_with_retry(
        &self,
        step: &WorkflowStep,
        step_index: usize,
        input: Option<&[u8]>,
        retry_policy: &RetryPolicy,
        executor: &dyn StepExecutor,
    ) -> Result<(Vec<u8>, u32), StepResult> {
        let max_attempts = retry_policy.total_attempts();
        let mut last_error = String::new();

        for attempt in 1..=max_attempts {
            match executor.execute_step(step, input) {
                Ok(output) => return Ok((output, attempt)),
                Err(msg) => {
                    last_error = msg;
                    if attempt < max_attempts {
                        // In a production engine, we would sleep here based on
                        // retry_policy.delay_for_attempt(attempt). For this
                        // deterministic engine, we retry immediately.
                        continue;
                    }
                }
            }
        }

        Err(StepResult::failed(
            step.name.clone(),
            step_index,
            max_attempts,
            last_error,
            0,
        ))
    }

    /// Runs SAGA compensation for all completed steps in reverse order.
    fn run_compensation(&self, instance: &mut WorkflowInstance, definition: &WorkflowDefinition) {
        // Build compensation keys list.
        let keys: Vec<Option<String>> = definition
            .steps
            .iter()
            .map(|s| s.compensation_key.clone())
            .collect();

        let errors = self.compensation_registry.compensate_steps(
            &instance.step_results,
            &keys,
        );

        // Transition to Compensating then Compensated.
        // If already Failed, we can transition to Compensating.
        if instance.status == WorkflowStatus::Failed {
            let _ = instance.transition_to(WorkflowStatus::Compensating);
        }

        // Mark all completed step results as compensated.
        for result in &mut instance.step_results {
            if result.status == StepStatus::Completed {
                result.status = StepStatus::Compensated;
            }
        }

        // BUG FIX: Track compensation errors properly.
        // If there were compensation failures, transition to Compensated but log errors.
        // Future: should add CompensatedWithErrors status for proper tracking.
        if !errors.is_empty() {
            log::warn!(
                "SAGA compensation completed with {} errors for workflow instance {:?}",
                errors.len(),
                instance.execution_id,
            );
            for err in &errors {
                log::error!("SAGA compensation error: {:?}", err);
            }
        }

        let _ = instance.transition_to(WorkflowStatus::Compensated);
    }

    /// Saves a checkpoint for the current instance state.
    fn save_checkpoint(&self, instance: &WorkflowInstance) -> Result<(), FlowError> {
        let checkpoint = Checkpoint::new(
            instance.definition_id,
            instance.execution_id,
            instance.current_step_index,
            instance.status,
            instance.step_results.clone(),
            self.clock_ms, // Use current clock value (already advanced)
        );
        self.checkpoint_store.save(checkpoint)
    }

    /// Returns the next monotonic timestamp and advances the clock.
    fn next_timestamp(&mut self) -> u64 {
        let ts = self.clock_ms;
        self.clock_ms += 1;
        ts
    }
}

impl Default for WorkflowEngine {
    fn default() -> Self {
        Self::new()
    }
}
