//! Integration tests for the workflow engine.

use zenic_proto::{ExecutionId, SessionId, TenantId, WorkflowId};

use crate::checkpoint::Checkpoint;
use crate::compensation::NoOpCompensation;
use crate::errors::FlowError;
use crate::retry::RetryPolicy;
use crate::status::{StepStatus, WorkflowStatus};
use crate::step::{StepResult, WorkflowStep};

use super::definition::WorkflowDefinition;
use super::executor::StepExecutor;
use super::instance::WorkflowInstance;
use super::store::CheckpointStore;
use super::workflow_engine::WorkflowEngine;

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
