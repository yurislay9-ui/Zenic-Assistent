// ─── Zenic-Agents v3 — Saga Definitions (Templates) ──────────────────
// USDT TRC20 ONLY. Saga definitions for each subscription lifecycle operation.

use crate::types::*;
use super::types::*;

/// Get the Saga definition for Trial Creation
pub fn trial_creation_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::TrialCreation,
        version: "1.0.0".to_string(),
        description: "Orchestrates the creation of a 14-day trial subscription for a new user. All users MUST start with trial.".to_string(),
        steps: vec![
            SagaStepDefinition {
                step_index: 0, step_name: "validate_email".to_string(),
                description: "Validate user email and check for existing trials".to_string(),
                action: "validate_email_uniqueness".to_string(), compensating_action: "none".to_string(),
                is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 1, step_name: "validate_wallet".to_string(),
                description: "Validate the TRC20 wallet address format".to_string(),
                action: "validate_trc20_address".to_string(), compensating_action: "none".to_string(),
                is_critical: true, timeout_ms: 3000, retry_count: 1, requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 2, step_name: "create_trial_record".to_string(),
                description: "Create the trial subscription record in the database".to_string(),
                action: "db_create_subscription".to_string(), compensating_action: "db_delete_subscription".to_string(),
                is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 3, step_name: "setup_feature_gates".to_string(),
                description: "Initialize feature gate access for Business tier (trial)".to_string(),
                action: "initialize_feature_gates".to_string(), compensating_action: "revoke_feature_gates".to_string(),
                is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 4, step_name: "create_audit_log".to_string(),
                description: "Create audit log entry for trial creation".to_string(),
                action: "create_audit_entry".to_string(), compensating_action: "mark_audit_as_rolled_back".to_string(),
                is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false,
            },
        ],
        timeout_ms: 60000, max_retries: 1,
        payment_currency: "USDT".to_string(), payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Trial → Paid Conversion
pub fn trial_conversion_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::TrialConversion,
        version: "1.0.0".to_string(),
        description: "Orchestrates converting a trial subscription to a paid tier with USDT TRC20 payment.".to_string(),
        steps: vec![
            SagaStepDefinition { step_index: 0, step_name: "validate_trial_active".to_string(), description: "Verify the trial subscription exists and is in trial status".to_string(), action: "validate_subscription_status".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 1, step_name: "validate_wallet_address".to_string(), description: "Validate the payer TRC20 wallet address".to_string(), action: "validate_trc20_address".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 3000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 2, step_name: "calculate_pricing".to_string(), description: "Calculate the first payment amount (monthly + setup fee)".to_string(), action: "calculate_subscription_pricing".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 3000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 3, step_name: "create_payment_request".to_string(), description: "Create a manual USDT TRC20 payment request record".to_string(), action: "db_create_payment_request".to_string(), compensating_action: "db_delete_payment_request".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 4, step_name: "update_subscription_record".to_string(), description: "Update subscription tier and status to paid".to_string(), action: "db_update_subscription".to_string(), compensating_action: "db_revert_subscription_to_trial".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 5, step_name: "update_feature_gates".to_string(), description: "Update feature gates for the new paid tier".to_string(), action: "update_feature_gates_for_tier".to_string(), compensating_action: "revert_feature_gates_to_trial".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 6, step_name: "create_conversion_audit".to_string(), description: "Create audit log for trial-to-paid conversion".to_string(), action: "create_audit_entry".to_string(), compensating_action: "mark_audit_as_rolled_back".to_string(), is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
        ],
        timeout_ms: 60000, max_retries: 1,
        payment_currency: "USDT".to_string(), payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Payment Verification
pub fn payment_verification_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::PaymentVerification,
        version: "1.0.0".to_string(),
        description: "Orchestrates manual/semi-manual verification of a USDT TRC20 payment.".to_string(),
        steps: vec![
            SagaStepDefinition { step_index: 0, step_name: "validate_tx_hash".to_string(), description: "Validate the TRC20 transaction hash format (64 hex chars)".to_string(), action: "validate_trc20_tx_hash".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 3000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 1, step_name: "check_payment_uniqueness".to_string(), description: "Ensure this tx_hash hasn't been used before (double-spend prevention)".to_string(), action: "check_tx_hash_uniqueness".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 2, step_name: "create_payment_record".to_string(), description: "Create the payment record in the database with awaiting_confirmation status".to_string(), action: "db_create_payment".to_string(), compensating_action: "db_delete_payment".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 3, step_name: "update_subscription_status".to_string(), description: "Update subscription status to pending_payment or active".to_string(), action: "db_update_subscription_status".to_string(), compensating_action: "db_revert_subscription_status".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 4, step_name: "await_admin_confirmation".to_string(), description: "Wait for admin to manually confirm the USDT TRC20 payment".to_string(), action: "await_admin_confirmation".to_string(), compensating_action: "mark_payment_as_expired".to_string(), is_critical: true, timeout_ms: 86400000, retry_count: 0, requires_external_input: true },
            SagaStepDefinition { step_index: 5, step_name: "finalize_payment".to_string(), description: "Finalize payment after admin confirmation, set subscription to active".to_string(), action: "finalize_payment_confirmation".to_string(), compensating_action: "revert_payment_to_awaiting".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 6, step_name: "create_payment_audit".to_string(), description: "Create audit log for the payment verification".to_string(), action: "create_audit_entry".to_string(), compensating_action: "mark_audit_as_rolled_back".to_string(), is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
        ],
        timeout_ms: 172800000, max_retries: 1,
        payment_currency: "USDT".to_string(), payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Subscription Cancellation
pub fn cancellation_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::Cancellation,
        version: "1.0.0".to_string(),
        description: "Orchestrates subscription cancellation with feature revocation and optional refund.".to_string(),
        steps: vec![
            SagaStepDefinition { step_index: 0, step_name: "validate_cancellation".to_string(), description: "Validate that the subscription can be cancelled".to_string(), action: "validate_subscription_cancellable".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 1, step_name: "update_subscription_cancelled".to_string(), description: "Update subscription status to cancelled in database".to_string(), action: "db_cancel_subscription".to_string(), compensating_action: "db_reactivate_subscription".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 2, step_name: "revoke_feature_gates".to_string(), description: "Revoke all feature gate access for the tenant".to_string(), action: "revoke_all_feature_gates".to_string(), compensating_action: "restore_feature_gates".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 3, step_name: "process_refund_if_applicable".to_string(), description: "Process USDT TRC20 refund if applicable (manual admin process)".to_string(), action: "initiate_refund_process".to_string(), compensating_action: "cancel_refund_process".to_string(), is_critical: false, timeout_ms: 30000, retry_count: 1, requires_external_input: true },
            SagaStepDefinition { step_index: 4, step_name: "create_cancellation_audit".to_string(), description: "Create audit log for the cancellation".to_string(), action: "create_audit_entry".to_string(), compensating_action: "mark_audit_as_rolled_back".to_string(), is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
        ],
        timeout_ms: 120000, max_retries: 1,
        payment_currency: "USDT".to_string(), payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Subscription Renewal
pub fn renewal_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::Renewal,
        version: "1.0.0".to_string(),
        description: "Orchestrates subscription renewal with payment verification and usage reset.".to_string(),
        steps: vec![
            SagaStepDefinition { step_index: 0, step_name: "validate_renewal".to_string(), description: "Validate that the subscription is eligible for renewal".to_string(), action: "validate_subscription_renewable".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 1, step_name: "create_renewal_payment_request".to_string(), description: "Create payment request for the renewal amount".to_string(), action: "db_create_payment_request".to_string(), compensating_action: "db_delete_payment_request".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 2, step_name: "await_payment_confirmation".to_string(), description: "Wait for admin to confirm USDT TRC20 renewal payment".to_string(), action: "await_admin_confirmation".to_string(), compensating_action: "mark_payment_as_expired".to_string(), is_critical: true, timeout_ms: 86400000, retry_count: 0, requires_external_input: true },
            SagaStepDefinition { step_index: 3, step_name: "extend_subscription_period".to_string(), description: "Extend the subscription period by 30 days".to_string(), action: "db_extend_subscription_period".to_string(), compensating_action: "db_revert_subscription_period".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 4, step_name: "reset_usage_records".to_string(), description: "Reset usage counters for the new billing period".to_string(), action: "db_reset_usage_records".to_string(), compensating_action: "db_restore_usage_records".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 5, step_name: "create_renewal_audit".to_string(), description: "Create audit log for the renewal".to_string(), action: "create_audit_entry".to_string(), compensating_action: "mark_audit_as_rolled_back".to_string(), is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
        ],
        timeout_ms: 172800000, max_retries: 1,
        payment_currency: "USDT".to_string(), payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Tier Upgrade
pub fn upgrade_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::Upgrade,
        version: "1.0.0".to_string(),
        description: "Orchestrates tier upgrade with proration calculation and feature activation.".to_string(),
        steps: vec![
            SagaStepDefinition { step_index: 0, step_name: "validate_upgrade".to_string(), description: "Validate that the upgrade is valid (new tier > current tier)".to_string(), action: "validate_upgrade_path".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 1, step_name: "calculate_proration".to_string(), description: "Calculate prorated amount for the upgrade".to_string(), action: "calculate_proration_amount".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 2, step_name: "create_upgrade_payment_request".to_string(), description: "Create payment request for the prorated upgrade amount".to_string(), action: "db_create_payment_request".to_string(), compensating_action: "db_delete_payment_request".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 3, step_name: "await_payment_confirmation".to_string(), description: "Wait for admin to confirm USDT TRC20 upgrade payment".to_string(), action: "await_admin_confirmation".to_string(), compensating_action: "mark_payment_as_expired".to_string(), is_critical: true, timeout_ms: 86400000, retry_count: 0, requires_external_input: true },
            SagaStepDefinition { step_index: 4, step_name: "update_subscription_tier".to_string(), description: "Update subscription to the new tier".to_string(), action: "db_update_subscription_tier".to_string(), compensating_action: "db_revert_subscription_tier".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 5, step_name: "activate_new_features".to_string(), description: "Activate features available in the new tier".to_string(), action: "update_feature_gates_for_tier".to_string(), compensating_action: "revert_feature_gates_to_previous_tier".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 6, step_name: "create_upgrade_audit".to_string(), description: "Create audit log for the upgrade".to_string(), action: "create_audit_entry".to_string(), compensating_action: "mark_audit_as_rolled_back".to_string(), is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
        ],
        timeout_ms: 172800000, max_retries: 1,
        payment_currency: "USDT".to_string(), payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Tier Downgrade
pub fn downgrade_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::Downgrade,
        version: "1.0.0".to_string(),
        description: "Orchestrates tier downgrade with feature revocation and proration credit.".to_string(),
        steps: vec![
            SagaStepDefinition { step_index: 0, step_name: "validate_downgrade".to_string(), description: "Validate that the downgrade is valid (new tier < current tier)".to_string(), action: "validate_downgrade_path".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 1, step_name: "identify_revocable_features".to_string(), description: "Identify features that will be revoked in the lower tier".to_string(), action: "identify_features_to_revoke".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 2, step_name: "calculate_proration_credit".to_string(), description: "Calculate prorated credit for the downgrade".to_string(), action: "calculate_proration_credit".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 3, step_name: "update_subscription_tier".to_string(), description: "Update subscription to the lower tier".to_string(), action: "db_update_subscription_tier".to_string(), compensating_action: "db_revert_subscription_tier".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 4, step_name: "revoke_features".to_string(), description: "Revoke features not available in the lower tier".to_string(), action: "revoke_features_for_downgrade".to_string(), compensating_action: "restore_revoked_features".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 5, step_name: "create_downgrade_audit".to_string(), description: "Create audit log for the downgrade".to_string(), action: "create_audit_entry".to_string(), compensating_action: "mark_audit_as_rolled_back".to_string(), is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
        ],
        timeout_ms: 120000, max_retries: 1,
        payment_currency: "USDT".to_string(), payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Subscription Reactivation
pub fn reactivation_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::Reactivation,
        version: "1.0.0".to_string(),
        description: "Orchestrates reactivation of a cancelled subscription.".to_string(),
        steps: vec![
            SagaStepDefinition { step_index: 0, step_name: "validate_reactivation".to_string(), description: "Validate that the subscription can be reactivated".to_string(), action: "validate_subscription_reactivatable".to_string(), compensating_action: "none".to_string(), is_critical: true, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
            SagaStepDefinition { step_index: 1, step_name: "create_reactivation_payment".to_string(), description: "Create payment request for reactivation".to_string(), action: "db_create_payment_request".to_string(), compensating_action: "db_delete_payment_request".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 2, step_name: "await_payment_confirmation".to_string(), description: "Wait for admin to confirm USDT TRC20 reactivation payment".to_string(), action: "await_admin_confirmation".to_string(), compensating_action: "mark_payment_as_expired".to_string(), is_critical: true, timeout_ms: 86400000, retry_count: 0, requires_external_input: true },
            SagaStepDefinition { step_index: 3, step_name: "reactivate_subscription".to_string(), description: "Update subscription status back to active".to_string(), action: "db_reactivate_subscription".to_string(), compensating_action: "db_cancel_subscription".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 4, step_name: "restore_feature_gates".to_string(), description: "Restore feature gate access for the tier".to_string(), action: "restore_feature_gates".to_string(), compensating_action: "revoke_all_feature_gates".to_string(), is_critical: true, timeout_ms: 10000, retry_count: 2, requires_external_input: false },
            SagaStepDefinition { step_index: 5, step_name: "create_reactivation_audit".to_string(), description: "Create audit log for the reactivation".to_string(), action: "create_audit_entry".to_string(), compensating_action: "mark_audit_as_rolled_back".to_string(), is_critical: false, timeout_ms: 5000, retry_count: 1, requires_external_input: false },
        ],
        timeout_ms: 172800000, max_retries: 1,
        payment_currency: "USDT".to_string(), payment_network: "TRC20".to_string(),
    }
}

/// Get a Saga definition by type
pub fn get_saga_definition(saga_type: SagaType) -> SagaDefinition {
    match saga_type {
        SagaType::TrialCreation => trial_creation_saga(),
        SagaType::TrialConversion => trial_conversion_saga(),
        SagaType::PaymentVerification => payment_verification_saga(),
        SagaType::Cancellation => cancellation_saga(),
        SagaType::Renewal => renewal_saga(),
        SagaType::Upgrade => upgrade_saga(),
        SagaType::Downgrade => downgrade_saga(),
        SagaType::Reactivation => reactivation_saga(),
    }
}
