//! SignupSaga: new user registration with automatic 14-day trial.
//!
//! Steps:
//! 1. validate_user — Verify user data is valid and no duplicate exists
//! 2. create_trial — Create a 14-day Business trial
//! 3. activate_trial — Activate the trial and grant Business access
//! 4. notify_user — Send welcome email with trial information
//!
//! Compensating actions (on failure, run in reverse):
//! 4. suppress_notification — Mark notification as cancelled
//! 3. deactivate_trial — Deactivate the trial
//! 2. delete_trial — Delete the trial record
//! 1. invalidate_user — Mark user record as invalid

use std::collections::HashMap;

use crate::errors::SubscriptionError;
use crate::saga::context::{SagaContext, SagaStepResult};
use crate::saga::{SagaExecutor, SagaStep, SubscriptionSaga};

// ---------------------------------------------------------------------------
// SignupSaga
// ---------------------------------------------------------------------------

/// Saga for new user signup with automatic 14-day trial.
///
/// Every new user gets a 14-day Business plan trial automatically.
/// No payment method is required to start the trial.
pub struct SignupSaga;

impl SubscriptionSaga for SignupSaga {
    fn name(&self) -> &str {
        "signup_saga"
    }

    fn execute(&self, context: &mut SagaContext) -> Result<Vec<SagaStepResult>, SubscriptionError> {
        let steps = vec![
            SagaStep {
                name: "validate_user".to_string(),
                action: Box::new(|ctx| {
                    // Validate user data.
                    if ctx.tenant_id.to_string().is_empty() {
                        return Err(SubscriptionError::Validation(
                            "tenant_id must not be empty".to_string(),
                        ));
                    }
                    // Check for duplicate (in production, check DB).
                    if ctx.get_data("user_exists") == Some("true") {
                        return Err(SubscriptionError::Validation(
                            "user already exists".to_string(),
                        ));
                    }
                    ctx.set_data("user_validated", "true");
                    Ok(SagaStepResult::success("validate_user"))
                }),
                compensation: Box::new(|ctx| {
                    // Mark user as invalidated.
                    ctx.set_data("user_validated", "false");
                    Ok(())
                }),
            },
            SagaStep {
                name: "create_trial".to_string(),
                action: Box::new(|ctx| {
                    // Create the 14-day trial.
                    ctx.subscription_status = crate::types::SubscriptionStatus::Trial;
                    ctx.current_tier = crate::types::SubscriptionTierName::Business;
                    ctx.set_data("trial_created", "true");
                    ctx.set_data("trial_days", "14");
                    Ok(SagaStepResult::success_with_data(
                        "create_trial",
                        HashMap::from([
                            ("trial_tier".to_string(), "Business".to_string()),
                            ("trial_days".to_string(), "14".to_string()),
                        ]),
                    ))
                }),
                compensation: Box::new(|ctx| {
                    // Delete the trial.
                    ctx.set_data("trial_created", "false");
                    ctx.subscription_status = crate::types::SubscriptionStatus::Expired;
                    Ok(())
                }),
            },
            SagaStep {
                name: "activate_trial".to_string(),
                action: Box::new(|ctx| {
                    // Activate the trial subscription.
                    if ctx.get_data("trial_created") != Some("true") {
                        return Err(SubscriptionError::InvalidState {
                            action: "activate_trial".to_string(),
                            state: "trial_not_created".to_string(),
                        });
                    }
                    ctx.set_data("trial_activated", "true");
                    Ok(SagaStepResult::success("activate_trial")
                        .with_data("access_level", "business")
                        .with_data("trial_active", "true"))
                }),
                compensation: Box::new(|ctx| {
                    // Deactivate the trial.
                    ctx.set_data("trial_activated", "false");
                    ctx.set_data("trial_active", "false");
                    Ok(())
                }),
            },
            SagaStep {
                name: "notify_user".to_string(),
                action: Box::new(|ctx| {
                    // Send welcome notification (in production, send email/push).
                    ctx.set_data("welcome_notification_sent", "true");
                    Ok(SagaStepResult::success("notify_user")
                        .with_data("notification_type", "welcome_trial")
                        .with_data("trial_days", "14"))
                }),
                compensation: Box::new(|ctx| {
                    // Suppress the notification.
                    ctx.set_data("welcome_notification_sent", "suppressed");
                    Ok(())
                }),
            },
        ];

        SagaExecutor::execute_steps(&steps, context)
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::SubscriptionTierName;
    use zenic_proto::TenantId;

    #[test]
    fn signup_saga_success() {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Starter);
        let saga = SignupSaga;

        let results = saga.execute(&mut ctx).expect("saga execution");

        assert_eq!(results.len(), 4);
        assert!(results.iter().all(|r| r.success));
        assert!(ctx.saga_completed);
        assert!(!ctx.saga_failed);
        assert_eq!(ctx.current_tier, SubscriptionTierName::Business);
        assert_eq!(ctx.subscription_status, crate::types::SubscriptionStatus::Trial);
        assert!(ctx.is_step_completed("validate_user"));
        assert!(ctx.is_step_completed("create_trial"));
        assert!(ctx.is_step_completed("activate_trial"));
        assert!(ctx.is_step_completed("notify_user"));
    }

    #[test]
    fn signup_saga_compensation_on_duplicate_user() {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Starter);
        ctx.set_data("user_exists", "true"); // Simulate duplicate user

        let saga = SignupSaga;
        let result = saga.execute(&mut ctx);

        assert!(result.is_err());
        assert!(ctx.saga_failed);
        assert_eq!(ctx.failed_step, Some("validate_user".to_string()));
        // No completed steps to compensate.
        assert!(ctx.compensated_steps.is_empty());
    }

    #[test]
    fn signup_saga_name() {
        let saga = SignupSaga;
        assert_eq!(saga.name(), "signup_saga");
    }
}
