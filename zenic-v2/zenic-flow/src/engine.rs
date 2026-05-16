//! Workflow engine: orchestrates durable workflow execution with
//! checkpoints, SAGA compensation, and retry with exponential backoff.
//!
//! The [`WorkflowEngine`] is the main entry point for executing durable
//! workflows. It coordinates:
//! - Sequential step execution through the [`StepExecutor`] trait
//! - Checkpoint persistence after each step
//! - Retry with configurable backoff policies
//! - SAGA compensation on unrecoverable failure
//!
//! The engine does NOT depend on `zenic-runtime` directly. The
//! [`StepExecutor`] trait abstracts step execution so that `zenic-core`
//! can provide an implementation backed by the runtime's DagScheduler.

use std::collections::HashMap;

use zenic_proto::{ExecutionId, SessionId, TenantId, WorkflowId};

use crate::checkpoint::Checkpoint;
use crate::compensation::{CompensationAction, CompensationRegistry};
use crate::errors::FlowError;
use crate::retry::RetryPolicy;
use crate::status::{StepStatus, WorkflowStatus};
use crate::step::{StepResult, WorkflowStep};

// ---------------------------------------------------------------------------
// StepExecutor trait
// ---------------------------------------------------------------------------

/// Trait for executing a single workflow step.
///
/// This trait abstracts the execution of a step so that the flow engine
/// remains independent of the runtime layer. The `zenic-core` crate
/// will implement this trait using `zenic-runtime`'s DagScheduler.
pub trait StepExecutor: Send + Sync {
    /// Executes a workflow step.
    ///
    /// - `step`: The step definition to execute.
    /// - `input`: Optional input data from the previous step's output.
    ///
    /// Returns the output data on success, or an error message on failure.
    fn execute_step(
        &self,
        step: &WorkflowStep,
        input: Option<&[u8]>,
    ) -> Result<Vec<u8>, String>;
}

// ---------------------------------------------------------------------------
// WorkflowDefinition
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// WorkflowInstance
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// CheckpointStore (with optional disk persistence)
// ---------------------------------------------------------------------------

/// Store for workflow checkpoints with optional disk persistence.
///
/// E-11 FIX: Added disk persistence so checkpoints survive process crashes.
/// Previously, checkpoints were stored in-memory only, meaning any crash
/// or restart would lose all workflow state. The store now supports:
///
/// - **In-memory mode** (`CheckpointStore::new()`): Same as before,
///   for testing and short-lived workflows.
/// - **Disk-persistent mode** (`CheckpointStore::with_persistence(dir)`):
///   Each checkpoint is serialized to `<dir>/<execution_id>.ckpt` using
///   bincode + zstd (the canonical format from `zenic-proto`). On startup,
///   existing checkpoint files are loaded back into memory.
///
/// Thread safety: Internal state is protected by `RwLock<HashMap>` so
/// concurrent reads are allowed. The `save()` and `remove()` methods
/// now take `&self` instead of `&mut self` (no longer need exclusive
/// access thanks to the internal lock).
pub struct CheckpointStore {
    /// In-memory index of checkpoints, protected by RwLock for thread safety.
    checkpoints: std::sync::RwLock<HashMap<ExecutionId, Checkpoint>>,
    /// Optional directory for disk persistence. If None, checkpoints are
    /// in-memory only (backward compatible with the original behavior).
    persist_dir: Option<std::path::PathBuf>,
}

impl CheckpointStore {
    /// Creates an empty in-memory checkpoint store (no disk persistence).
    ///
    /// This is the original behavior, suitable for testing and short-lived
    /// workflows where crash recovery is not required.
    pub fn new() -> Self {
        Self {
            checkpoints: std::sync::RwLock::new(HashMap::new()),
            persist_dir: None,
        }
    }

    /// Creates a checkpoint store with disk persistence.
    ///
    /// E-11 FIX: Checkpoints are saved to individual files in the given
    /// directory, one per execution. The directory is created if it doesn't
    /// exist. On construction, any existing checkpoint files in the
    /// directory are loaded into memory.
    ///
    /// File format: `<dir>/<execution_id_hex>.ckpt` — bincode + zstd
    /// serialized `Checkpoint` structs (same as `Checkpoint::to_bytes()`).
    ///
    /// # Errors
    ///
    /// Returns `FlowError` if the directory cannot be created or if
    /// existing checkpoint files cannot be read.
    pub fn with_persistence(dir: impl Into<std::path::PathBuf>) -> Result<Self, FlowError> {
        let persist_dir = dir.into();
        std::fs::create_dir_all(&persist_dir).map_err(|e| {
            FlowError::CheckpointFailed(format!(
                "failed to create checkpoint directory {:?}: {}",
                persist_dir, e
            ))
        })?;

        let store = Self {
            checkpoints: std::sync::RwLock::new(HashMap::new()),
            persist_dir: Some(persist_dir),
        };

        // Load existing checkpoints from disk.
        store.load_from_disk()?;

        Ok(store)
    }

    /// Saves a checkpoint, replacing any previous checkpoint for the same execution.
    ///
    /// If disk persistence is enabled, the checkpoint is also written to disk.
    /// The in-memory store is always updated first, then the disk write is
    /// attempted. If the disk write fails, a warning is logged but the
    /// in-memory store is still updated (graceful degradation).
    pub fn save(&self, checkpoint: Checkpoint) -> Result<(), FlowError> {
        let exec_id = checkpoint.execution_id;

        // Update in-memory store.
        {
            let mut map = self.checkpoints.write().map_err(|e| {
                FlowError::CheckpointFailed(format!("lock poisoned: {}", e))
            })?;
            map.insert(exec_id, checkpoint.clone());
        }

        // Persist to disk if enabled.
        if let Some(ref dir) = self.persist_dir {
            if let Err(e) = self.persist_checkpoint(&exec_id, &checkpoint) {
                log::warn!(
                    "E-11: Failed to persist checkpoint {:?} to disk: {}. \
                     In-memory checkpoint is still valid.",
                    exec_id, e
                );
            }
        }

        Ok(())
    }

    /// Loads the latest checkpoint for an execution ID.
    ///
    /// Returns a reference to the checkpoint from the in-memory store.
    /// For disk-persistent stores, checkpoints are loaded into memory
    /// on construction, so this always returns from memory.
    pub fn load(&self, execution_id: &ExecutionId) -> Option<Checkpoint> {
        let map = self.checkpoints.read().ok()?;
        map.get(execution_id).cloned()
    }

    /// Removes and returns the checkpoint for an execution ID.
    ///
    /// If disk persistence is enabled, the checkpoint file is also removed.
    pub fn remove(&self, execution_id: &ExecutionId) -> Option<Checkpoint> {
        let cp = {
            let mut map = self.checkpoints.write().ok()?;
            map.remove(execution_id)
        };

        // Remove from disk if enabled.
        if let Some(ref dir) = self.persist_dir {
            let path = dir.join(format!("{}.ckpt", execution_id));
            let _ = std::fs::remove_file(path); // Best-effort removal
        }

        cp
    }

    /// Returns the number of stored checkpoints.
    pub fn len(&self) -> usize {
        self.checkpoints.read().map(|m| m.len()).unwrap_or(0)
    }

    /// Whether the store is empty.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Whether disk persistence is enabled.
    pub fn is_persistent(&self) -> bool {
        self.persist_dir.is_some()
    }

    // -----------------------------------------------------------------------
    // Private helpers for disk persistence
    // -----------------------------------------------------------------------

    /// Persists a single checkpoint to disk.
    fn persist_checkpoint(
        &self,
        execution_id: &ExecutionId,
        checkpoint: &Checkpoint,
    ) -> Result<(), FlowError> {
        let dir = self.persist_dir.as_ref().ok_or_else(|| {
            FlowError::CheckpointFailed("persistence not enabled".to_string())
        })?;

        let bytes = checkpoint.to_bytes()?;
        let path = dir.join(format!("{}.ckpt", execution_id));

        // Write atomically: write to temp file, then rename.
        let temp_path = dir.join(format!("{}.ckpt.tmp", execution_id));
        std::fs::write(&temp_path, &bytes).map_err(|e| {
            FlowError::CheckpointFailed(format!(
                "failed to write checkpoint to {:?}: {}",
                temp_path, e
            ))
        })?;
        std::fs::rename(&temp_path, &path).map_err(|e| {
            FlowError::CheckpointFailed(format!(
                "failed to rename checkpoint from {:?} to {:?}: {}",
                temp_path, path, e
            ))
        })?;

        Ok(())
    }

    /// Loads all checkpoint files from the persistence directory.
    fn load_from_disk(&self) -> Result<(), FlowError> {
        let dir = self.persist_dir.as_ref().ok_or_else(|| {
            FlowError::CheckpointFailed("persistence not enabled".to_string())
        })?;

        let entries = std::fs::read_dir(dir).map_err(|e| {
            FlowError::CheckpointFailed(format!(
                "failed to read checkpoint directory {:?}: {}",
                dir, e
            ))
        })?;

        let mut loaded = 0usize;
        let mut errors = 0usize;

        for entry in entries {
            let entry = match entry {
                Ok(e) => e,
                Err(_) => continue,
            };

            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("ckpt") {
                continue;
            }

            match std::fs::read(&path) {
                Ok(bytes) => match Checkpoint::from_bytes(&bytes) {
                    Ok(checkpoint) => {
                        let exec_id = checkpoint.execution_id;
                        if let Ok(mut map) = self.checkpoints.write() {
                            map.insert(exec_id, checkpoint);
                        }
                        loaded += 1;
                    }
                    Err(e) => {
                        log::warn!(
                            "E-11: Failed to deserialize checkpoint from {:?}: {}. Skipping.",
                            path, e
                        );
                        errors += 1;
                    }
                },
                Err(e) => {
                    log::warn!(
                        "E-11: Failed to read checkpoint file {:?}: {}. Skipping.",
                        path, e
                    );
                    errors += 1;
                }
            }
        }

        if loaded > 0 || errors > 0 {
            log::info!(
                "E-11: CheckpointStore loaded {} checkpoints from disk ({} errors) in {:?}",
                loaded, errors, dir
            );
        }

        Ok(())
    }
}

impl Default for CheckpointStore {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// WorkflowEngine
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::compensation::NoOpCompensation;

    // -----------------------------------------------------------------------
    // Test helpers
    // -----------------------------------------------------------------------

    /// A step executor that always succeeds with empty output.
    struct AlwaysSuccessExecutor;

    impl StepExecutor for AlwaysSuccessExecutor {
        fn execute_step(
            &self,
            _step: &WorkflowStep,
            _input: Option<&[u8]>,
        ) -> Result<Vec<u8>, String> {
            Ok(vec![])
        }
    }

    /// A step executor that always fails.
    struct AlwaysFailExecutor {
        message: String,
    }

    impl StepExecutor for AlwaysFailExecutor {
        fn execute_step(
            &self,
            _step: &WorkflowStep,
            _input: Option<&[u8]>,
        ) -> Result<Vec<u8>, String> {
            Err(self.message.clone())
        }
    }

    /// A step executor that fails on the first N attempts for a given step.
    struct FailThenSuccessExecutor {
        fail_count: std::sync::atomic::AtomicU32,
    }

    impl FailThenSuccessExecutor {
        fn new(fail_count: u32) -> Self {
            Self {
                fail_count: std::sync::atomic::AtomicU32::new(fail_count),
            }
        }
    }

    impl StepExecutor for FailThenSuccessExecutor {
        fn execute_step(
            &self,
            _step: &WorkflowStep,
            _input: Option<&[u8]>,
        ) -> Result<Vec<u8>, String> {
            let remaining = self.fail_count.fetch_sub(1, std::sync::atomic::Ordering::SeqCst);
            if remaining > 0 {
                Err("transient failure".to_string())
            } else {
                Ok(vec![42])
            }
        }
    }

    fn make_simple_definition(step_count: usize) -> WorkflowDefinition {
        let steps: Vec<WorkflowStep> = (0..step_count)
            .map(|i| WorkflowStep::new(&format!("step_{}", i), &format!("Step {}", i)))
            .collect();
        WorkflowDefinition::new(
            WorkflowId::new(),
            "test_workflow",
            "A test workflow",
            steps,
            RetryPolicy::no_retry(),
        )
    }

    fn make_definition_with_compensation() -> WorkflowDefinition {
        let steps = vec![
            WorkflowStep::new("step_0", "First step").compensation_key("comp_0"),
            WorkflowStep::new("step_1", "Second step").compensation_key("comp_1"),
            WorkflowStep::new("step_2", "Third step"),
        ];
        WorkflowDefinition::new(
            WorkflowId::new(),
            "compensating_workflow",
            "A workflow with compensation",
            steps,
            RetryPolicy::no_retry(),
        )
    }

    // -----------------------------------------------------------------------
    // WorkflowDefinition tests
    // -----------------------------------------------------------------------

    #[test]
    fn definition_validate_valid() {
        let def = make_simple_definition(3);
        assert!(def.validate().is_ok());
    }

    #[test]
    fn definition_validate_empty_name() {
        let mut def = make_simple_definition(1);
        def.name = String::new();
        assert!(def.validate().is_err());
    }

    #[test]
    fn definition_validate_no_steps() {
        let def = WorkflowDefinition::new(
            WorkflowId::new(),
            "empty",
            "No steps",
            vec![],
            RetryPolicy::no_retry(),
        );
        assert!(def.validate().is_err());
    }

    #[test]
    fn definition_validate_duplicate_step_names() {
        let steps = vec![
            WorkflowStep::new("duplicate", "First"),
            WorkflowStep::new("duplicate", "Second"),
        ];
        let def = WorkflowDefinition::new(
            WorkflowId::new(),
            "bad",
            "Duplicate names",
            steps,
            RetryPolicy::no_retry(),
        );
        assert!(def.validate().is_err());
    }

    #[test]
    fn definition_retry_policy_for_step() {
        let custom_policy = RetryPolicy::new(5, 100, 10_000, 3.0);
        let steps = vec![
            WorkflowStep::new("step_0", "Default policy"),
            WorkflowStep::new("step_1", "Custom policy").retry_policy(custom_policy.clone()),
        ];
        let def = WorkflowDefinition::new(
            WorkflowId::new(),
            "test",
            "test",
            steps,
            RetryPolicy::default(),
        );

        let step0_policy = def.retry_policy_for_step(0);
        assert_eq!(step0_policy.max_retries, RetryPolicy::default().max_retries);

        let step1_policy = def.retry_policy_for_step(1);
        assert_eq!(step1_policy.max_retries, 5);
    }

    // -----------------------------------------------------------------------
    // WorkflowInstance tests
    // -----------------------------------------------------------------------

    #[test]
    fn instance_new_is_pending() {
        let instance = WorkflowInstance::new(
            WorkflowId::new(),
            ExecutionId::new(),
            SessionId::new(),
            TenantId::new(),
            0,
        );
        assert_eq!(instance.status, WorkflowStatus::Pending);
        assert_eq!(instance.current_step_index, 0);
        assert!(instance.step_results.is_empty());
        assert!(!instance.is_terminal());
        assert!(!instance.is_success());
    }

    #[test]
    fn instance_transition_valid() {
        let mut instance = WorkflowInstance::new(
            WorkflowId::new(),
            ExecutionId::new(),
            SessionId::new(),
            TenantId::new(),
            0,
        );
        instance.transition_to(WorkflowStatus::Running).expect("transition");
        assert_eq!(instance.status, WorkflowStatus::Running);
        instance.transition_to(WorkflowStatus::Completed).expect("transition");
        assert!(instance.is_success());
        assert!(instance.is_terminal());
    }

    #[test]
    fn instance_transition_invalid() {
        let mut instance = WorkflowInstance::new(
            WorkflowId::new(),
            ExecutionId::new(),
            SessionId::new(),
            TenantId::new(),
            0,
        );
        let result = instance.transition_to(WorkflowStatus::Completed);
        assert!(result.is_err());
    }

    // -----------------------------------------------------------------------
    // CheckpointStore tests
    // -----------------------------------------------------------------------

    #[test]
    fn checkpoint_store_save_and_load() {
        let store = CheckpointStore::new();
        let exec_id = ExecutionId::new();
        let cp = Checkpoint::initial(WorkflowId::new(), exec_id, 0);
        store.save(cp).expect("save");
        assert_eq!(store.len(), 1);
        let loaded = store.load(&exec_id);
        assert!(loaded.is_some());
    }

    #[test]
    fn checkpoint_store_remove() {
        let store = CheckpointStore::new();
        let exec_id = ExecutionId::new();
        let cp = Checkpoint::initial(WorkflowId::new(), exec_id, 0);
        store.save(cp).expect("save");
        let removed = store.remove(&exec_id);
        assert!(removed.is_some());
        assert!(store.is_empty());
    }

    #[test]
    fn checkpoint_store_default_is_new() {
        let store = CheckpointStore::default();
        assert!(store.is_empty());
    }

    // -----------------------------------------------------------------------
    // WorkflowEngine: successful execution
    // -----------------------------------------------------------------------

    #[test]
    fn engine_execute_single_step_success() {
        let def = make_simple_definition(1);
        let mut engine = WorkflowEngine::new();
        let executor = AlwaysSuccessExecutor;

        let instance = engine
            .execute(&def, &executor, SessionId::new(), TenantId::new())
            .expect("execute");

        assert!(instance.is_success());
        assert_eq!(instance.step_results.len(), 1);
        assert_eq!(instance.step_results[0].status, StepStatus::Completed);
        assert_eq!(engine.checkpoint_count(), 1); // HashMap stores latest only per execution
    }

    #[test]
    fn engine_execute_multiple_steps_success() {
        let def = make_simple_definition(3);
        let mut engine = WorkflowEngine::new();
        let executor = AlwaysSuccessExecutor;

        let instance = engine
            .execute(&def, &executor, SessionId::new(), TenantId::new())
            .expect("execute");

        assert!(instance.is_success());
        assert_eq!(instance.completed_step_count(), 3);
        assert_eq!(instance.step_results.len(), 3);
        for result in &instance.step_results {
            assert_eq!(result.status, StepStatus::Completed);
        }
    }

    // -----------------------------------------------------------------------
    // WorkflowEngine: failure and compensation
    // -----------------------------------------------------------------------

    #[test]
    fn engine_execute_step_failure_triggers_compensation() {
        let def = make_definition_with_compensation();
        let mut engine = WorkflowEngine::new();
        engine
            .register_compensation("comp_0", Box::new(NoOpCompensation::new("comp_0")))
            .expect("register");
        engine
            .register_compensation("comp_1", Box::new(NoOpCompensation::new("comp_1")))
            .expect("register");

        // Use AlwaysFailExecutor to ensure first step fails and triggers compensation.
        let executor = AlwaysFailExecutor {
            message: "step failed".to_string(),
        };

        let instance = engine
            .execute(&def, &executor, SessionId::new(), TenantId::new())
            .expect("execute");

        // First step fails, workflow should be compensated.
        assert_eq!(instance.status, WorkflowStatus::Compensated);
        assert!(!instance.is_success());
    }

    // -----------------------------------------------------------------------
    // WorkflowEngine: retry
    // -----------------------------------------------------------------------

    #[test]
    fn engine_retry_succeeds_after_transient_failure() {
        let steps = vec![WorkflowStep::new("retry_step", "Step with retry")
            .retry_policy(RetryPolicy::new(2, 10, 100, 2.0))];
        let def = WorkflowDefinition::new(
            WorkflowId::new(),
            "retry_workflow",
            "Workflow with retry",
            steps,
            RetryPolicy::no_retry(),
        );

        let mut engine = WorkflowEngine::new();
        // Fail once, then succeed.
        let executor = FailThenSuccessExecutor::new(1);

        let instance = engine
            .execute(&def, &executor, SessionId::new(), TenantId::new())
            .expect("execute");

        assert!(instance.is_success());
        assert_eq!(instance.step_results[0].attempts, 2);
    }

    #[test]
    fn engine_retry_exhausted() {
        let steps = vec![WorkflowStep::new("retry_step", "Step with retry")
            .retry_policy(RetryPolicy::new(2, 10, 100, 2.0))];
        let def = WorkflowDefinition::new(
            WorkflowId::new(),
            "retry_exhausted",
            "Workflow with exhausted retry",
            steps,
            RetryPolicy::no_retry(),
        );

        let mut engine = WorkflowEngine::new();
        let executor = AlwaysFailExecutor {
            message: "permanent failure".to_string(),
        };

        let instance = engine
            .execute(&def, &executor, SessionId::new(), TenantId::new())
            .expect("execute");

        assert!(!instance.is_success());
        assert_eq!(instance.status, WorkflowStatus::Compensated);
        assert_eq!(instance.step_results[0].attempts, 3); // 1 initial + 2 retries
    }

    // -----------------------------------------------------------------------
    // WorkflowEngine: checkpoints
    // -----------------------------------------------------------------------

    #[test]
    fn engine_saves_checkpoints_during_execution() {
        let def = make_simple_definition(2);
        let mut engine = WorkflowEngine::new();
        let executor = AlwaysSuccessExecutor;

        let instance = engine
            .execute(&def, &executor, SessionId::new(), TenantId::new())
            .expect("execute");

        // Should have checkpoints: initial, step_0, step_1, completed
        assert!(engine.checkpoint_count() > 0);

        let cp = engine.get_checkpoint(&instance.execution_id).expect("checkpoint");
        assert_eq!(cp.workflow_status, WorkflowStatus::Completed);
    }

    // -----------------------------------------------------------------------
    // WorkflowEngine: resume from checkpoint
    // -----------------------------------------------------------------------

    #[test]
    fn engine_resume_from_checkpoint() {
        let def = make_simple_definition(2);
        let mut engine = WorkflowEngine::new();
        let executor = AlwaysSuccessExecutor;

        // Execute first.
        let instance = engine
            .execute(&def, &executor, SessionId::new(), TenantId::new())
            .expect("execute");

        // Get checkpoint (which is the completed one).
        let cp = engine.get_checkpoint(&instance.execution_id).expect("checkpoint").clone();

        // Resuming a completed checkpoint should fail.
        let result = engine.resume_from_checkpoint(cp, &def, &executor);
        assert!(result.is_err());
    }

    // -----------------------------------------------------------------------
    // WorkflowEngine: validation
    // -----------------------------------------------------------------------

    #[test]
    fn engine_rejects_invalid_definition() {
        let def = WorkflowDefinition::new(
            WorkflowId::new(),
            "",
            "No name",
            vec![WorkflowStep::new("step", "Step")],
            RetryPolicy::no_retry(),
        );
        let mut engine = WorkflowEngine::new();
        let executor = AlwaysSuccessExecutor;

        let result = engine.execute(&def, &executor, SessionId::new(), TenantId::new());
        assert!(result.is_err());
    }

    #[test]
    fn engine_default_is_new() {
        let engine = WorkflowEngine::default();
        assert_eq!(engine.checkpoint_count(), 0);
    }
}
