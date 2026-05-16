//! CancellationSaga: subscription cancellation with refund handling.
//!
//! Steps:
//! 1. revoke_access — Revoke all feature access for the subscription
//! 2. cancel_subscription — Mark the subscription as cancelled
//! 3. process_refund — Process USDT TRC20 refund (manual)
//! 4. notify_user — Send cancellation confirmation
//!
//! Compensating actions (on failure):
//! 4. suppress_notification — Suppress cancellation notification
//! 3. reverse_refund — Mark refund as reversed
//! 2. reactivate_subscription — Reactivate the subscription
//! 1. restore_access — Restore feature access

use std::collections::HashMap;

use crate::errors::SubscriptionError;
use crate::saga::context::{SagaContext, SagaStepResult};
use crate::saga::{SagaExecutor, SagaStep, SubscriptionSaga};

// ---------------------------------------------------------------------------
// CancellationSaga
// ---------------------------------------------------------------------------

/// Saga for cancelling a subscription.
///
/// Handles access revocation, subscription state change, refund processing,
/// and user notification. If any step fails, compensating actions restore
/// the previous state.
pub struct CancellationSaga;

impl SubscriptionSaga for CancellationSaga {
    fn name(&self) -> &str {
        "cancellation_saga"
    }

    fn execute(&self, context: &mut SagaContext) -> Result<Vec<SagaStepResult>, SubscriptionError> {
        // Validate the subscription is in a cancellable state.
        if context.subscription_status.is_terminal() {
            return Err(SubscriptionError::InvalidState {
                action: "cancel subscription".to_string(),
                state: context.subscription_status.to_string(),
            });
        }

        let steps = vec![
            SagaStep {
                name: "revoke_access".to_string(),
                action: Box::new(|ctx| {
                    // Revoke all feature access.
                    let previous_access = ctx.get_data("access_granted").unwrap_or("unknown").to_string();
                    ctx.set_data("access_granted", "false");
                    ctx.set_data("features_unlocked", "false");
                    ctx.set_data("previous_access", &previous_access);

                    Ok(SagaStepResult::success("revoke_access")
                        .with_data("access_revoked", "true"))
                }),
                compensation: Box::new(|ctx| {
                    // Restore access.
                    let previous = ctx.get_data("previous_access").unwrap_or("false").to_string();
                    ctx.set_data("access_granted", &previous);
                    ctx.set_data("features_unlocked", &previous);
                    Ok(())
                }),
            },
            SagaStep {
                name: "cancel_subscription".to_string(),
                action: Box::new(|ctx| {
                    // Mark subscription as cancelled.
                    let previous_status = ctx.subscription_status.to_string();
                    ctx.subscription_status = crate::types::SubscriptionStatus::Cancelled;
                    ctx.set_data("subscription_cancelled", "true");
                    ctx.set_data("previous_status", &previous_status);

                    Ok(SagaStepResult::success_with_data(
                        "cancel_subscription",
                        HashMap::from([
                            ("previous_status".to_string(), previous_status),
                            ("cancelled_tier".to_string(), ctx.current_tier.to_string()),
                        ]),
                    ))
                }),
                compensation: Box::new(|ctx| {
                    // Reactivate subscription.
                    ctx.subscription_status = crate::types::SubscriptionStatus::Active;
                    ctx.set_data("subscription_cancelled", "false");
                    Ok(())
                }),
            },
            SagaStep {
                name: "process_refund".to_string(),
                action: Box::new(|ctx| {
                    // Process USDT TRC20 refund.
                    // In production: create refund transaction on TRON.
                    // Refunds are manual: admin sends USDT back to customer wallet.
                    let refund_amount = ctx.amount_usdt.unwrap_or(0);

                    if refund_amount > 0 {
                        ctx.set_data("refund_initiated", "true");
                        ctx.set_data("refund_amount", &refund_amount.to_string());
                        ctx.set_data("refund_method", "usdt_trc20_manual");
                    } else {
                        ctx.set_data("refund_initiated", "false");
                        ctx.set_data("refund_reason", "no_amount_to_refund");
                    }

                    Ok(SagaStepResult::success("process_refund")
                        .with_data("refund_amount_usdt", &refund_amount.to_string())
                        .with_data("refund_method", "usdt_trc20"))
                }),
                compensation: Box::new(|ctx| {
                    // Reverse refund.
                    ctx.set_data("refund_initiated", "reversed");
                    Ok(())
                }),
            },
            SagaStep {
                name: "notify_user".to_string(),
                action: Box::new(|ctx| {
                    // Send cancellation notification.
                    ctx.set_data("cancellation_notification_sent", "true");

                    Ok(SagaStepResult::success("notify_user")
                        .with_data("notification_type", "subscription_cancelled")
                        .with_data("refund_status", ctx.get_data("refund_initiated").unwrap_or("unknown")))
                }),
                compensation: Box::new(|ctx| {
                    // Suppress notification.
                    ctx.set_data("cancellation_notification_sent", "suppressed");
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
    use crate::types::{SubscriptionTierName, SubscriptionStatus};
    use zenic_proto::TenantId;

    #[test]
    fn cancellation_saga_success() {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Business);
        ctx.subscription_status = SubscriptionStatus::Active;
        ctx.amount_usdt = Some(99);

        let saga = CancellationSaga;
        let results = saga.execute(&mut ctx).expect("saga execution");

        assert_eq!(results.len(), 4);
        assert!(results.iter().all(|r| r.success));
        assert!(ctx.saga_completed);
        assert_eq!(ctx.subscription_status, SubscriptionStatus::Cancelled);
        assert_eq!(ctx.get_data("subscription_cancelled"), Some("true"));
        assert_eq!(ctx.get_data("refund_initiated"), Some("true"));
    }

    #[test]
    fn cancellation_saga_already_cancelled() {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Business);
        ctx.subscription_status = SubscriptionStatus::Cancelled;

        let saga = CancellationSaga;
        let result = saga.execute(&mut ctx);

        assert!(result.is_err());
    }

    #[test]
    fn cancellation_saga_no_refund() {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Business);
        ctx.subscription_status = SubscriptionStatus::Active;
        // No amount_usdt set (trial user).

        let saga = CancellationSaga;
        let results = saga.execute(&mut ctx).expect("saga execution");

        assert_eq!(results.len(), 4);
        assert_eq!(ctx.get_data("refund_initiated"), Some("false"));
    }

    #[test]
    fn cancellation_saga_name() {
        let saga = CancellationSaga;
        assert_eq!(saga.name(), "cancellation_saga");
    }
}
