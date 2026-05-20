//! PaymentSaga: USDT TRC20 payment processing with Saga pattern.
//!
//! Steps:
//! 1. verify_payment — Verify USDT TRC20 transaction on TRON blockchain
//! 2. apply_subscription — Apply the subscription tier to the user's account
//! 3. grant_access — Grant feature access based on the tier
//! 4. update_audit — Record the payment in the Merkle audit log
//!
//! Compensating actions (on failure):
//! 4. revert_audit — Remove the audit entry
//! 3. revoke_access — Revoke feature access
//! 2. revert_subscription — Revert the subscription to previous state
//! 1. mark_payment_failed — Mark the payment as failed

use std::collections::HashMap;

use crate::errors::SubscriptionError;
use crate::saga::context::{SagaContext, SagaStepResult};
use crate::saga::{SagaExecutor, SagaStep, SubscriptionSaga};

// ---------------------------------------------------------------------------
// PaymentSaga
// ---------------------------------------------------------------------------

/// Saga for processing USDT TRC20 payments.
///
/// Supports both manual and semi-manual payment processing.
/// The saga verifies the on-chain transaction, applies the subscription,
/// grants access, and records the audit trail.
pub struct PaymentSaga;

impl SubscriptionSaga for PaymentSaga {
    fn name(&self) -> &str {
        "payment_saga"
    }

    fn execute(&self, context: &mut SagaContext) -> Result<Vec<SagaStepResult>, SubscriptionError> {
        let steps = vec![
            SagaStep {
                name: "verify_payment".to_string(),
                action: Box::new(|ctx| {
                    // Verify USDT TRC20 payment.
                    let tx_hash = ctx.tx_hash.clone().ok_or_else(|| {
                        SubscriptionError::InvalidTxHash("missing tx_hash".to_string())
                    })?;

                    // Basic validation: TRON tx hash is 64 hex chars.
                    if tx_hash.len() != 64 || !tx_hash.chars().all(|c| c.is_ascii_hexdigit()) {
                        return Err(SubscriptionError::InvalidTxHash(tx_hash));
                    }

                    let wallet = ctx.wallet_address.clone().ok_or_else(|| {
                        SubscriptionError::InvalidWalletAddress("missing wallet_address".to_string())
                    })?;

                    // Basic TRON address validation.
                    if !wallet.starts_with('T') || wallet.len() != 34 {
                        return Err(SubscriptionError::InvalidWalletAddress(wallet));
                    }

                    // Verify amount.
                    let expected = ctx.amount_usdt.ok_or_else(|| {
                        SubscriptionError::Validation("missing amount_usdt".to_string())
                    })?;

                    // In production: query TRON blockchain for tx details.
                    // For now: accept if all validations pass.
                    ctx.set_data("payment_verified", "true");
                    ctx.set_data("verified_amount", &expected.to_string());

                    Ok(SagaStepResult::success_with_data(
                        "verify_payment",
                        HashMap::from([
                            ("tx_hash".to_string(), tx_hash),
                            ("amount_usdt".to_string(), expected.to_string()),
                            ("payment_method".to_string(), "usdt_trc20".to_string()),
                        ]),
                    ))
                }),
                compensation: Box::new(|ctx| {
                    // Mark payment as failed.
                    ctx.set_data("payment_verified", "false");
                    ctx.set_data("payment_status", "failed");
                    Ok(())
                }),
            },
            SagaStep {
                name: "apply_subscription".to_string(),
                action: Box::new(|ctx| {
                    // Apply the subscription tier.
                    if ctx.get_data("payment_verified") != Some("true") {
                        return Err(SubscriptionError::InvalidState {
                            action: "apply_subscription".to_string(),
                            state: "payment_not_verified".to_string(),
                        });
                    }

                    let previous_tier = ctx.current_tier.to_string();
                    let target_tier = ctx.target_tier.unwrap_or(ctx.current_tier);

                    ctx.current_tier = target_tier;
                    ctx.subscription_status = crate::types::SubscriptionStatus::Active;
                    ctx.set_data("subscription_applied", "true");
                    ctx.set_data("previous_tier", &previous_tier);
                    ctx.set_data("new_tier", &target_tier.to_string());

                    Ok(SagaStepResult::success_with_data(
                        "apply_subscription",
                        HashMap::from([
                            ("previous_tier".to_string(), previous_tier),
                            ("new_tier".to_string(), target_tier.to_string()),
                        ]),
                    ))
                }),
                compensation: Box::new(|ctx| {
                    // Revert to previous state.
                    // Note: In production, restore the exact previous tier from stored data.
                    ctx.set_data("subscription_applied", "false");
                    ctx.subscription_status = crate::types::SubscriptionStatus::Trial;
                    Ok(())
                }),
            },
            SagaStep {
                name: "grant_access".to_string(),
                action: Box::new(|ctx| {
                    // Grant feature access based on the tier.
                    if ctx.get_data("subscription_applied") != Some("true") {
                        return Err(SubscriptionError::InvalidState {
                            action: "grant_access".to_string(),
                            state: "subscription_not_applied".to_string(),
                        });
                    }

                    ctx.set_data("access_granted", "true");
                    ctx.set_data("access_tier", &ctx.current_tier.to_string());

                    Ok(SagaStepResult::success("grant_access")
                        .with_data("access_level", &ctx.current_tier.to_string())
                        .with_data("features_unlocked", "true"))
                }),
                compensation: Box::new(|ctx| {
                    // Revoke access.
                    ctx.set_data("access_granted", "false");
                    ctx.set_data("features_unlocked", "false");
                    Ok(())
                }),
            },
            SagaStep {
                name: "update_audit".to_string(),
                action: Box::new(|ctx| {
                    // Record in Merkle audit log.
                    // In production: append to Merkle tree and persist.
                    ctx.set_data("audit_recorded", "true");

                    Ok(SagaStepResult::success("update_audit")
                        .with_data("audit_entry", "payment_processed")
                        .with_data("payment_method", "usdt_trc20"))
                }),
                compensation: Box::new(|ctx| {
                    // Remove audit entry.
                    ctx.set_data("audit_recorded", "false");
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

    fn make_valid_context() -> SagaContext {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Starter);
        ctx.target_tier = Some(SubscriptionTierName::Business);
        ctx.amount_usdt = Some(99);
        ctx.tx_hash = Some("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2".to_string());
        ctx.wallet_address = Some("TXYZabcd1234abcd1234abcd1234abcd12".to_string());
        ctx
    }

    #[test]
    fn payment_saga_success() {
        let mut ctx = make_valid_context();
        let saga = PaymentSaga;

        let results = saga.execute(&mut ctx).expect("saga execution");

        assert_eq!(results.len(), 4);
        assert!(results.iter().all(|r| r.success));
        assert!(ctx.saga_completed);
        assert_eq!(ctx.current_tier, SubscriptionTierName::Business);
        assert_eq!(ctx.subscription_status, crate::types::SubscriptionStatus::Active);
    }

    #[test]
    fn payment_saga_missing_tx_hash() {
        let mut ctx = make_valid_context();
        ctx.tx_hash = None;

        let saga = PaymentSaga;
        let result = saga.execute(&mut ctx);

        assert!(result.is_err());
        assert!(ctx.saga_failed);
        assert_eq!(ctx.failed_step, Some("verify_payment".to_string()));
    }

    #[test]
    fn payment_saga_invalid_tx_hash() {
        let mut ctx = make_valid_context();
        ctx.tx_hash = Some("invalid".to_string());

        let saga = PaymentSaga;
        let result = saga.execute(&mut ctx);

        assert!(result.is_err());
        assert!(ctx.saga_failed);
    }

    #[test]
    fn payment_saga_missing_wallet() {
        let mut ctx = make_valid_context();
        ctx.wallet_address = None;

        let saga = PaymentSaga;
        let result = saga.execute(&mut ctx);

        assert!(result.is_err());
    }

    #[test]
    fn payment_saga_missing_amount() {
        let mut ctx = make_valid_context();
        ctx.amount_usdt = None;

        let saga = PaymentSaga;
        let result = saga.execute(&mut ctx);

        assert!(result.is_err());
    }

    #[test]
    fn payment_saga_name() {
        let saga = PaymentSaga;
        assert_eq!(saga.name(), "payment_saga");
    }
}
