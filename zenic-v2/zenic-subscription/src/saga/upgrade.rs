//! UpgradeSaga: subscription tier upgrade with proration.
//!
//! Steps:
//! 1. validate_upgrade — Validate that the upgrade is valid
//! 2. calculate_proration — Calculate prorated cost for the upgrade
//! 3. verify_payment — Verify USDT TRC20 payment for the upgrade
//! 4. apply_new_tier — Apply the new tier to the subscription
//! 5. update_access — Update feature access for the new tier
//! 6. update_audit — Record the upgrade in the Merkle audit log

use std::collections::HashMap;

use crate::errors::SubscriptionError;
use crate::pricing::PricingEngine;
use crate::saga::context::{SagaContext, SagaStepResult};
use crate::saga::{SagaExecutor, SagaStep, SubscriptionSaga};
use crate::types::SubscriptionTierName;

// ---------------------------------------------------------------------------
// UpgradeSaga
// ---------------------------------------------------------------------------

/// Saga for upgrading a subscription tier.
///
/// Handles validation, proration calculation, payment verification,
/// tier application, access updates, and audit recording.
pub struct UpgradeSaga;

impl SubscriptionSaga for UpgradeSaga {
    fn name(&self) -> &str {
        "upgrade_saga"
    }

    fn execute(&self, context: &mut SagaContext) -> Result<Vec<SagaStepResult>, SubscriptionError> {
        let steps = vec![
            SagaStep {
                name: "validate_upgrade".to_string(),
                action: Box::new(|ctx| {
                    let from_tier = ctx.current_tier;
                    let to_tier = ctx.target_tier.ok_or_else(|| {
                        SubscriptionError::Validation("missing target_tier for upgrade".to_string())
                    })?;

                    // Validate this is an actual upgrade.
                    if !to_tier.is_upgrade_from(&from_tier) {
                        return Err(SubscriptionError::Validation(format!(
                            "upgrade from {} to {} is not valid (not an upgrade)",
                            from_tier, to_tier
                        )));
                    }

                    // Validate subscription is active.
                    if !ctx.subscription_status.is_active() {
                        return Err(SubscriptionError::InvalidState {
                            action: "upgrade".to_string(),
                            state: ctx.subscription_status.to_string(),
                        });
                    }

                    ctx.set_data("upgrade_validated", "true");
                    ctx.set_data("from_tier", &from_tier.to_string());
                    ctx.set_data("to_tier", &to_tier.to_string());

                    Ok(SagaStepResult::success_with_data(
                        "validate_upgrade",
                        HashMap::from([
                            ("from_tier".to_string(), from_tier.to_string()),
                            ("to_tier".to_string(), to_tier.to_string()),
                        ]),
                    ))
                }),
                compensation: Box::new(|ctx| {
                    ctx.set_data("upgrade_validated", "false");
                    Ok(())
                }),
            },
            SagaStep {
                name: "calculate_proration".to_string(),
                action: Box::new(|ctx| {
                    if ctx.get_data("upgrade_validated") != Some("true") {
                        return Err(SubscriptionError::InvalidState {
                            action: "calculate_proration".to_string(),
                            state: "upgrade_not_validated".to_string(),
                        });
                    }

                    let from_tier = ctx.current_tier;
                    let to_tier = ctx.target_tier.unwrap_or(from_tier);

                    let days_remaining = ctx.days_remaining.unwrap_or(0);
                    let days_in_period = ctx.days_in_period.unwrap_or(30);

                    let proration = PricingEngine::calculate_upgrade_proration(
                        from_tier,
                        to_tier,
                        days_remaining,
                        days_in_period,
                    );

                    ctx.proration_amount = Some(proration);
                    ctx.set_data("proration_calculated", "true");
                    ctx.set_data("proration_amount_usdt", &proration.to_string());

                    Ok(SagaStepResult::success_with_data(
                        "calculate_proration",
                        HashMap::from([
                            ("from_tier".to_string(), from_tier.to_string()),
                            ("to_tier".to_string(), to_tier.to_string()),
                            ("proration_usdt".to_string(), proration.to_string()),
                            ("days_remaining".to_string(), days_remaining.to_string()),
                        ]),
                    ))
                }),
                compensation: Box::new(|ctx| {
                    ctx.proration_amount = None;
                    ctx.set_data("proration_calculated", "false");
                    Ok(())
                }),
            },
            SagaStep {
                name: "verify_payment".to_string(),
                action: Box::new(|ctx| {
                    // Verify payment for the prorated amount.
                    let proration = ctx.proration_amount.unwrap_or(0);

                    // If proration is 0 (shouldn't happen for upgrades), skip.
                    if proration == 0 {
                        ctx.set_data("upgrade_payment_verified", "true");
                        ctx.set_data("upgrade_payment_amount", "0");
                        return Ok(SagaStepResult::success("verify_payment")
                            .with_data("amount_usdt", "0")
                            .with_data("reason", "no_proration"));
                    }

                    // Verify USDT TRC20 payment.
                    let tx_hash = ctx.tx_hash.clone().ok_or_else(|| {
                        SubscriptionError::InvalidTxHash("missing tx_hash for upgrade payment".to_string())
                    })?;

                    // In production: verify on TRON blockchain.
                    ctx.set_data("upgrade_payment_verified", "true");
                    ctx.set_data("upgrade_payment_amount", &proration.to_string());

                    Ok(SagaStepResult::success_with_data(
                        "verify_payment",
                        HashMap::from([
                            ("tx_hash".to_string(), tx_hash),
                            ("amount_usdt".to_string(), proration.to_string()),
                            ("payment_method".to_string(), "usdt_trc20".to_string()),
                        ]),
                    ))
                }),
                compensation: Box::new(|ctx| {
                    ctx.set_data("upgrade_payment_verified", "false");
                    Ok(())
                }),
            },
            SagaStep {
                name: "apply_new_tier".to_string(),
                action: Box::new(|ctx| {
                    if ctx.get_data("upgrade_payment_verified") != Some("true") {
                        return Err(SubscriptionError::InvalidState {
                            action: "apply_new_tier".to_string(),
                            state: "payment_not_verified".to_string(),
                        });
                    }

                    let previous_tier = ctx.current_tier;
                    let new_tier = ctx.target_tier.unwrap_or(previous_tier);

                    ctx.current_tier = new_tier;
                    ctx.set_data("new_tier_applied", "true");
                    ctx.set_data("tier_upgraded_from", &previous_tier.to_string());
                    ctx.set_data("tier_upgraded_to", &new_tier.to_string());

                    Ok(SagaStepResult::success_with_data(
                        "apply_new_tier",
                        HashMap::from([
                            ("previous_tier".to_string(), previous_tier.to_string()),
                            ("new_tier".to_string(), new_tier.to_string()),
                        ]),
                    ))
                }),
                compensation: Box::new(|ctx| {
                    // Revert to previous tier.
                    let prev = ctx.get_data("tier_upgraded_from").unwrap_or("Starter");
                    ctx.current_tier = match prev {
                        "Business" => SubscriptionTierName::Business,
                        "Enterprise" => SubscriptionTierName::Enterprise,
                        "OnPremiseEnterprise" => SubscriptionTierName::OnPremiseEnterprise,
                        _ => SubscriptionTierName::Starter,
                    };
                    ctx.set_data("new_tier_applied", "false");
                    Ok(())
                }),
            },
            SagaStep {
                name: "update_access".to_string(),
                action: Box::new(|ctx| {
                    if ctx.get_data("new_tier_applied") != Some("true") {
                        return Err(SubscriptionError::InvalidState {
                            action: "update_access".to_string(),
                            state: "new_tier_not_applied".to_string(),
                        });
                    }

                    // Update feature access for the new tier.
                    ctx.set_data("access_updated", "true");
                    ctx.set_data("access_tier", &ctx.current_tier.to_string());
                    ctx.set_data("features_unlocked", "true");

                    Ok(SagaStepResult::success("update_access")
                        .with_data("new_access_level", &ctx.current_tier.to_string()))
                }),
                compensation: Box::new(|ctx| {
                    ctx.set_data("access_updated", "false");
                    ctx.set_data("features_unlocked", "false");
                    Ok(())
                }),
            },
            SagaStep {
                name: "update_audit".to_string(),
                action: Box::new(|ctx| {
                    // Record upgrade in Merkle audit log.
                    ctx.set_data("upgrade_audit_recorded", "true");

                    Ok(SagaStepResult::success("update_audit")
                        .with_data("audit_type", "tier_upgrade")
                        .with_data("from_tier", ctx.get_data("tier_upgraded_from").unwrap_or("unknown"))
                        .with_data("to_tier", ctx.get_data("tier_upgraded_to").unwrap_or("unknown")))
                }),
                compensation: Box::new(|ctx| {
                    ctx.set_data("upgrade_audit_recorded", "false");
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
    use crate::types::SubscriptionStatus;
    use zenic_proto::TenantId;

    #[test]
    fn upgrade_saga_starter_to_business() {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Starter);
        ctx.subscription_status = SubscriptionStatus::Active;
        ctx.target_tier = Some(SubscriptionTierName::Business);
        ctx.days_remaining = Some(15);
        ctx.days_in_period = Some(30);
        ctx.tx_hash = Some("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2".to_string());

        let saga = UpgradeSaga;
        let results = saga.execute(&mut ctx).expect("saga execution");

        assert_eq!(results.len(), 6);
        assert!(results.iter().all(|r| r.success));
        assert!(ctx.saga_completed);
        assert_eq!(ctx.current_tier, SubscriptionTierName::Business);
        assert!(ctx.proration_amount.is_some());
        assert!(ctx.proration_amount.unwrap() > 0);
    }

    #[test]
    fn upgrade_saga_business_to_enterprise() {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Business);
        ctx.subscription_status = SubscriptionStatus::Active;
        ctx.target_tier = Some(SubscriptionTierName::Enterprise);
        ctx.days_remaining = Some(10);
        ctx.days_in_period = Some(30);
        ctx.tx_hash = Some("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2".to_string());

        let saga = UpgradeSaga;
        let results = saga.execute(&mut ctx).expect("saga execution");

        assert_eq!(results.len(), 6);
        assert_eq!(ctx.current_tier, SubscriptionTierName::Enterprise);
    }

    #[test]
    fn upgrade_saga_downgrade_fails() {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Business);
        ctx.subscription_status = SubscriptionStatus::Active;
        ctx.target_tier = Some(SubscriptionTierName::Starter); // This is a downgrade!

        let saga = UpgradeSaga;
        let result = saga.execute(&mut ctx);

        assert!(result.is_err());
        assert!(ctx.saga_failed);
        assert_eq!(ctx.failed_step, Some("validate_upgrade".to_string()));
    }

    #[test]
    fn upgrade_saga_missing_target_tier() {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Starter);
        ctx.subscription_status = SubscriptionStatus::Active;
        // No target_tier set.

        let saga = UpgradeSaga;
        let result = saga.execute(&mut ctx);

        assert!(result.is_err());
    }

    #[test]
    fn upgrade_saga_inactive_subscription() {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Starter);
        ctx.subscription_status = SubscriptionStatus::Cancelled;
        ctx.target_tier = Some(SubscriptionTierName::Business);

        let saga = UpgradeSaga;
        let result = saga.execute(&mut ctx);

        assert!(result.is_err());
    }

    #[test]
    fn upgrade_saga_name() {
        let saga = UpgradeSaga;
        assert_eq!(saga.name(), "upgrade_saga");
    }
}
