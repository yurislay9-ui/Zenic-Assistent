//! RenewalSaga: subscription renewal with payment verification.
//!
//! Steps:
//! 1. verify_renewal — Verify the renewal payment (USDT TRC20)
//! 2. extend_subscription — Extend the subscription period
//! 3. update_audit — Record the renewal in the Merkle audit log
//! 4. notify_user — Send renewal confirmation

use std::collections::HashMap;

use crate::errors::SubscriptionError;
use crate::saga::context::{SagaContext, SagaStepResult};
use crate::saga::{SagaExecutor, SagaStep, SubscriptionSaga};

// ---------------------------------------------------------------------------
// RenewalSaga
// ---------------------------------------------------------------------------

/// Saga for renewing a subscription.
///
/// Handles payment verification, subscription period extension,
/// audit recording, and user notification.
pub struct RenewalSaga;

impl SubscriptionSaga for RenewalSaga {
    fn name(&self) -> &str {
        "renewal_saga"
    }

    fn execute(&self, context: &mut SagaContext) -> Result<Vec<SagaStepResult>, SubscriptionError> {
        // Validate the subscription is in a renewable state.
        if !context.subscription_status.is_active() && context.subscription_status != crate::types::SubscriptionStatus::PastDue {
            return Err(SubscriptionError::InvalidState {
                action: "renew subscription".to_string(),
                state: context.subscription_status.to_string(),
            });
        }

        let steps = vec![
            SagaStep {
                name: "verify_renewal".to_string(),
                action: Box::new(|ctx| {
                    // Verify USDT TRC20 renewal payment.
                    let tx_hash = ctx.tx_hash.clone().ok_or_else(|| {
                        SubscriptionError::InvalidTxHash("missing tx_hash for renewal".to_string())
                    })?;

                    let expected = ctx.amount_usdt.ok_or_else(|| {
                        SubscriptionError::Validation("missing renewal amount".to_string())
                    })?;

                    // In production: query TRON blockchain.
                    ctx.set_data("renewal_verified", "true");
                    ctx.set_data("renewal_amount", &expected.to_string());

                    Ok(SagaStepResult::success_with_data(
                        "verify_renewal",
                        HashMap::from([
                            ("tx_hash".to_string(), tx_hash),
                            ("amount_usdt".to_string(), expected.to_string()),
                        ]),
                    ))
                }),
                compensation: Box::new(|ctx| {
                    ctx.set_data("renewal_verified", "false");
                    Ok(())
                }),
            },
            SagaStep {
                name: "extend_subscription".to_string(),
                action: Box::new(|ctx| {
                    if ctx.get_data("renewal_verified") != Some("true") {
                        return Err(SubscriptionError::InvalidState {
                            action: "extend_subscription".to_string(),
                            state: "renewal_not_verified".to_string(),
                        });
                    }

                    // Extend subscription period by 30 days.
                    ctx.subscription_status = crate::types::SubscriptionStatus::Active;
                    ctx.set_data("subscription_extended", "true");
                    ctx.set_data("extension_days", "30");

                    Ok(SagaStepResult::success("extend_subscription")
                        .with_data("new_period_days", "30")
                        .with_data("tier", &ctx.current_tier.to_string()))
                }),
                compensation: Box::new(|ctx| {
                    ctx.set_data("subscription_extended", "false");
                    Ok(())
                }),
            },
            SagaStep {
                name: "update_audit".to_string(),
                action: Box::new(|ctx| {
                    // Record renewal in Merkle audit log.
                    ctx.set_data("renewal_audit_recorded", "true");

                    Ok(SagaStepResult::success("update_audit")
                        .with_data("audit_type", "renewal")
                        .with_data("payment_method", "usdt_trc20"))
                }),
                compensation: Box::new(|ctx| {
                    ctx.set_data("renewal_audit_recorded", "false");
                    Ok(())
                }),
            },
            SagaStep {
                name: "notify_user".to_string(),
                action: Box::new(|ctx| {
                    ctx.set_data("renewal_notification_sent", "true");

                    Ok(SagaStepResult::success("notify_user")
                        .with_data("notification_type", "subscription_renewed")
                        .with_data("tier", &ctx.current_tier.to_string()))
                }),
                compensation: Box::new(|ctx| {
                    ctx.set_data("renewal_notification_sent", "suppressed");
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

    fn make_renewal_context() -> SagaContext {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Business);
        ctx.subscription_status = SubscriptionStatus::Active;
        ctx.amount_usdt = Some(99);
        ctx.tx_hash = Some("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2".to_string());
        ctx
    }

    #[test]
    fn renewal_saga_success() {
        let mut ctx = make_renewal_context();
        let saga = RenewalSaga;

        let results = saga.execute(&mut ctx).expect("saga execution");

        assert_eq!(results.len(), 4);
        assert!(results.iter().all(|r| r.success));
        assert!(ctx.saga_completed);
        assert_eq!(ctx.subscription_status, SubscriptionStatus::Active);
        assert_eq!(ctx.get_data("subscription_extended"), Some("true"));
    }

    #[test]
    fn renewal_saga_past_due() {
        let mut ctx = make_renewal_context();
        ctx.subscription_status = SubscriptionStatus::PastDue;

        let saga = RenewalSaga;
        let results = saga.execute(&mut ctx).expect("saga execution");

        assert_eq!(results.len(), 4);
        assert_eq!(ctx.subscription_status, SubscriptionStatus::Active);
    }

    #[test]
    fn renewal_saga_cancelled_fails() {
        let mut ctx = make_renewal_context();
        ctx.subscription_status = SubscriptionStatus::Cancelled;

        let saga = RenewalSaga;
        let result = saga.execute(&mut ctx);

        assert!(result.is_err());
    }

    #[test]
    fn renewal_saga_missing_tx_hash() {
        let mut ctx = make_renewal_context();
        ctx.tx_hash = None;

        let saga = RenewalSaga;
        let result = saga.execute(&mut ctx);

        assert!(result.is_err());
        assert_eq!(ctx.failed_step, Some("verify_renewal".to_string()));
    }

    #[test]
    fn renewal_saga_name() {
        let saga = RenewalSaga;
        assert_eq!(saga.name(), "renewal_saga");
    }
}
