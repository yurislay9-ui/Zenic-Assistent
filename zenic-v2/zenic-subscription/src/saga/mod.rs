//! Saga pattern for subscription lifecycle reliability.
//!
//! The Saga pattern ensures that multi-step subscription operations either
//! complete fully or are compensated (rolled back) on failure. This prevents
//! partial state inconsistencies in the subscription system.
//!
//! ## Subscription Sagas
//!
//! - **SignupSaga**: validate_user → create_trial → activate_trial → notify_user
//! - **PaymentSaga**: verify_payment → apply_subscription → grant_access → update_audit
//! - **CancellationSaga**: revoke_access → cancel_subscription → process_refund → notify_user
//! - **RenewalSaga**: verify_renewal → extend_subscription → update_audit → notify_user
//! - **UpgradeSaga**: validate_upgrade → calculate_proration → apply_new_tier → update_access → update_audit

pub mod cancellation;
pub mod context;
pub mod payment;
pub mod renewal;
pub mod signup;
pub mod upgrade;

// Re-exports.
pub use cancellation::CancellationSaga;
pub use context::{SagaContext, SagaStepResult};
pub use payment::PaymentSaga;
pub use renewal::RenewalSaga;
pub use signup::SignupSaga;
pub use upgrade::UpgradeSaga;

use crate::errors::SubscriptionError;

// ---------------------------------------------------------------------------
// SubscriptionSaga trait
// ---------------------------------------------------------------------------

/// Trait for subscription sagas.
///
/// Each saga implements this trait to provide:
/// - A list of steps with compensating actions
/// - Execution that runs steps sequentially
/// - Automatic compensation on failure
pub trait SubscriptionSaga: Send + Sync {
    /// Human-readable name of this saga.
    fn name(&self) -> &str;

    /// Executes the saga, running all steps sequentially.
    /// On failure, runs compensating actions in reverse order.
    fn execute(&self, context: &mut SagaContext) -> Result<Vec<SagaStepResult>, SubscriptionError>;
}

// ---------------------------------------------------------------------------
// SagaStep
// ---------------------------------------------------------------------------

/// A single step in a subscription saga.
pub struct SagaStep {
    /// Step name (unique within the saga).
    pub name: String,
    /// The action to execute.
    pub action: Box<dyn Fn(&mut SagaContext) -> Result<SagaStepResult, SubscriptionError> + Send + Sync>,
    /// The compensating action (undo) for this step.
    pub compensation: Box<dyn Fn(&mut SagaContext) -> Result<(), SubscriptionError> + Send + Sync>,
}

impl std::fmt::Debug for SagaStep {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SagaStep")
            .field("name", &self.name)
            .finish()
    }
}

// ---------------------------------------------------------------------------
// SagaExecutor (shared execution logic)
// ---------------------------------------------------------------------------

/// Executes a list of saga steps with automatic compensation on failure.
pub struct SagaExecutor;

impl SagaExecutor {
    /// Executes steps sequentially, compensating on failure.
    ///
    /// If a step fails:
    /// 1. All previously completed steps are compensated in reverse order.
    /// 2. Compensation errors are logged but don't stop the compensation process.
    /// 3. The original error is returned.
    pub fn execute_steps(
        steps: &[SagaStep],
        context: &mut SagaContext,
    ) -> Result<Vec<SagaStepResult>, SubscriptionError> {
        let mut results = Vec::new();
        let mut completed_steps: Vec<&SagaStep> = Vec::new();

        for step in steps {
            context.current_step = Some(step.name.clone());

            match (step.action)(context) {
                Ok(result) => {
                    context.completed_steps.push(step.name.clone());
                    completed_steps.push(step);
                    results.push(result);
                }
                Err(error) => {
                    // Step failed: compensate all completed steps in reverse order.
                    context.saga_failed = true;
                    context.failed_step = Some(step.name.clone());
                    context.failure_reason = Some(error.to_string());

                    let mut compensation_errors = Vec::new();
                    for comp_step in completed_steps.iter().rev() {
                        if let Err(comp_err) = (comp_step.compensation)(context) {
                            compensation_errors.push(format!(
                                "compensation for '{}' failed: {}",
                                comp_step.name, comp_err
                            ));
                        } else {
                            context.compensated_steps.push(comp_step.name.clone());
                        }
                    }

                    if compensation_errors.is_empty() {
                        return Err(SubscriptionError::SagaCompensated {
                            step: step.name.clone(),
                            reason: error.to_string(),
                        });
                    } else {
                        return Err(SubscriptionError::SagaCompensationFailed {
                            step: step.name.clone(),
                            reason: format!(
                                "original: {}; compensation errors: {}",
                                error,
                                compensation_errors.join("; ")
                            ),
                        });
                    }
                }
            }
        }

        context.saga_completed = true;
        Ok(results)
    }
}
