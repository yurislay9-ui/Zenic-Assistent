// ─── Saga Execution Logic ────────────────────────────────────────────────
// create_saga_execution, advance_saga_step, complete_compensation_step

use super::definitions::get_saga_definition;
use super::pricing::{chrono_now_iso, sha256_short};
use super::types::*;

/// Initialize a new Saga execution from a definition
pub fn create_saga_execution(
    saga_type: SagaType,
    tenant_id: String,
    subscription_id: Option<String>,
    metadata: Option<String>,
) -> SagaExecution {
    let definition = get_saga_definition(saga_type);
    let now = chrono_now_iso();
    let execution_id = format!("saga_{}_{}", definition.saga_type.as_str(), sha256_short(&format!("{}:{}", tenant_id, &now)));

    let steps: Vec<SagaStepExecution> = definition.steps.iter().map(|step_def| {
        SagaStepExecution {
            step_index: step_def.step_index,
            step_name: step_def.step_name.clone(),
            status: SagaStepStatus::Pending,
            started_at: None,
            completed_at: None,
            error_message: None,
            input_data: None,
            output_data: None,
            compensation_started_at: None,
            compensation_completed_at: None,
            compensation_error: None,
            retry_count: 0,
        }
    }).collect();

    SagaExecution {
        execution_id,
        saga_type: definition.saga_type,
        status: SagaStatus::Pending,
        tenant_id,
        subscription_id,
        steps,
        current_step_index: 0,
        started_at: now,
        completed_at: None,
        error_message: None,
        compensation_reason: None,
        metadata,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
    }
}

/// Process a step completion in a Saga execution
pub fn advance_saga_step(
    execution: &mut SagaExecution,
    step_index: u32,
    success: bool,
    output_data: Option<String>,
    error_message: Option<String>,
) -> SagaStatus {
    let now = chrono_now_iso();

    if (step_index as usize) >= execution.steps.len() {
        execution.status = SagaStatus::Failed;
        execution.error_message = Some(format!("Step index {} out of bounds", step_index));
        return execution.status;
    }

    let step = &mut execution.steps[step_index as usize];

    if success {
        step.status = SagaStepStatus::Completed;
        step.completed_at = Some(now.clone());
        step.output_data = output_data;
        step.error_message = None;
    } else {
        step.status = SagaStepStatus::Failed;
        step.completed_at = Some(now.clone());
        step.error_message = error_message;
    }

    // Determine next action
    if success {
        // Check if this was the last step
        if step_index as usize == execution.steps.len() - 1 {
            execution.status = SagaStatus::Completed;
            execution.completed_at = Some(now);
        } else {
            execution.current_step_index = step_index + 1;
            execution.steps[step_index as usize + 1].status = SagaStepStatus::Running;
            execution.steps[step_index as usize + 1].started_at = Some(now);
            execution.status = SagaStatus::Running;
        }
    } else {
        // Check if step is critical
        let definition = get_saga_definition(execution.saga_type);
        let step_def = &definition.steps[step_index as usize];

        if step_def.is_critical {
            // Start compensation
            execution.status = SagaStatus::Compensating;
            execution.compensation_reason = Some(format!("Step '{}' failed: {}", step.step_name, step.error_message.clone().unwrap_or_default()));
            execution.current_step_index = step_index;
        } else {
            // Non-critical failure, continue to next step
            if step_index as usize == execution.steps.len() - 1 {
                execution.status = SagaStatus::Completed;
                execution.completed_at = Some(now);
            } else {
                execution.current_step_index = step_index + 1;
                execution.steps[step_index as usize + 1].status = SagaStepStatus::Running;
                execution.steps[step_index as usize + 1].started_at = Some(now);
                execution.status = SagaStatus::Running;
            }
        }
    }

    execution.status
}

/// Process a compensation step completion
pub fn complete_compensation_step(
    execution: &mut SagaExecution,
    step_index: u32,
    success: bool,
    compensation_error: Option<String>,
) -> SagaStatus {
    let now = chrono_now_iso();

    if (step_index as usize) >= execution.steps.len() {
        execution.status = SagaStatus::Failed;
        return execution.status;
    }

    let step = &mut execution.steps[step_index as usize];

    if success {
        step.status = SagaStepStatus::Compensated;
        step.compensation_completed_at = Some(now.clone());
    } else {
        step.compensation_error = compensation_error;
        // Compensation failed - this is a critical error
        execution.status = SagaStatus::Failed;
        execution.error_message = Some(format!("Compensation failed at step '{}': {}", step.step_name, step.compensation_error.clone().unwrap_or_default()));
        return execution.status;
    }

    // Move to the previous step for compensation
    if step_index > 0 {
        let prev_index = step_index - 1;
        execution.steps[prev_index as usize].status = SagaStepStatus::Compensating;
        execution.steps[prev_index as usize].compensation_started_at = Some(now.clone());
        execution.current_step_index = prev_index;
        execution.status = SagaStatus::Compensating;
    } else {
        // All compensations complete
        execution.status = SagaStatus::Compensated;
        execution.completed_at = Some(now);
    }

    execution.status
}
