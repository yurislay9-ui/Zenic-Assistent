// ─── Zenic-Agents v3 — Saga Pattern for Subscription Engine ────────────
// USDT TRC20 ONLY. All subscription lifecycle operations are managed as
// Sagas with compensating actions for rollback on failure.
//
// The Saga pattern ensures that multi-step subscription operations are
// either fully completed or fully rolled back. This is CRITICAL for:
// - Trial creation (wallet validation → subscription record → feature gates → audit)
// - Trial-to-paid conversion (validate → payment → update → feature gates → audit)
// - Payment verification (validate tx → create payment → update status → audit)
// - Cancellation (validate → update status → revoke features → refund if needed → audit)
// - Renewal (validate → extend period → reset usage → audit)
// - Upgrade (validate → prorate → update tier → update features → payment → audit)
// - Downgrade (validate → identify revocations → update tier → revoke features → audit)

use serde::{Deserialize, Serialize};
use crate::types::*;

// ═══════════════════════════════════════════════════════════════════════════
// Saga Core Types
// ═══════════════════════════════════════════════════════════════════════════

/// Unique identifier for each Saga type
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SagaType {
    TrialCreation,
    TrialConversion,
    PaymentVerification,
    Cancellation,
    Renewal,
    Upgrade,
    Downgrade,
    Reactivation,
}

impl SagaType {
    pub fn as_str(&self) -> &'static str {
        match self {
            SagaType::TrialCreation => "trial_creation",
            SagaType::TrialConversion => "trial_conversion",
            SagaType::PaymentVerification => "payment_verification",
            SagaType::Cancellation => "cancellation",
            SagaType::Renewal => "renewal",
            SagaType::Upgrade => "upgrade",
            SagaType::Downgrade => "downgrade",
            SagaType::Reactivation => "reactivation",
        }
    }

    pub fn display_name(&self) -> &'static str {
        match self {
            SagaType::TrialCreation => "Trial Creation Saga",
            SagaType::TrialConversion => "Trial → Paid Conversion Saga",
            SagaType::PaymentVerification => "Payment Verification Saga",
            SagaType::Cancellation => "Subscription Cancellation Saga",
            SagaType::Renewal => "Subscription Renewal Saga",
            SagaType::Upgrade => "Tier Upgrade Saga",
            SagaType::Downgrade => "Tier Downgrade Saga",
            SagaType::Reactivation => "Subscription Reactivation Saga",
        }
    }

    pub fn description(&self) -> &'static str {
        match self {
            SagaType::TrialCreation => "Orchestrates the creation of a 14-day trial subscription for a new user",
            SagaType::TrialConversion => "Orchestrates converting a trial subscription to a paid tier with USDT TRC20 payment",
            SagaType::PaymentVerification => "Orchestrates manual/semi-manual verification of a USDT TRC20 payment",
            SagaType::Cancellation => "Orchestrates subscription cancellation with feature revocation and optional refund",
            SagaType::Renewal => "Orchestrates subscription renewal with payment verification and usage reset",
            SagaType::Upgrade => "Orchestrates tier upgrade with proration and feature activation",
            SagaType::Downgrade => "Orchestrates tier downgrade with feature revocation and proration credit",
            SagaType::Reactivation => "Orchestrates reactivation of a cancelled subscription",
        }
    }

    pub fn all() -> Vec<SagaType> {
        vec![
            SagaType::TrialCreation,
            SagaType::TrialConversion,
            SagaType::PaymentVerification,
            SagaType::Cancellation,
            SagaType::Renewal,
            SagaType::Upgrade,
            SagaType::Downgrade,
            SagaType::Reactivation,
        ]
    }

    pub fn from_str_value(s: &str) -> Option<SagaType> {
        match s.to_lowercase().as_str() {
            "trial_creation" => Some(SagaType::TrialCreation),
            "trial_conversion" => Some(SagaType::TrialConversion),
            "payment_verification" => Some(SagaType::PaymentVerification),
            "cancellation" => Some(SagaType::Cancellation),
            "renewal" => Some(SagaType::Renewal),
            "upgrade" => Some(SagaType::Upgrade),
            "downgrade" => Some(SagaType::Downgrade),
            "reactivation" => Some(SagaType::Reactivation),
            _ => None,
        }
    }
}

/// Status of a Saga execution
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SagaStatus {
    Pending,        // Saga created, not yet started
    Running,        // Currently executing steps
    Completed,      // All steps completed successfully
    Compensating,   // A step failed, running compensating actions
    Compensated,    // All compensating actions completed (rolled back)
    Failed,         // Saga failed and compensation also failed
    TimedOut,       // Saga exceeded time limit
    Paused,         // Saga paused (awaiting external input, e.g. admin confirmation)
}

impl SagaStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            SagaStatus::Pending => "pending",
            SagaStatus::Running => "running",
            SagaStatus::Completed => "completed",
            SagaStatus::Compensating => "compensating",
            SagaStatus::Compensated => "compensated",
            SagaStatus::Failed => "failed",
            SagaStatus::TimedOut => "timed_out",
            SagaStatus::Paused => "paused",
        }
    }

    pub fn is_terminal(&self) -> bool {
        matches!(self, SagaStatus::Completed | SagaStatus::Compensated | SagaStatus::Failed | SagaStatus::TimedOut)
    }

    pub fn from_str_value(s: &str) -> Option<SagaStatus> {
        match s.to_lowercase().as_str() {
            "pending" => Some(SagaStatus::Pending),
            "running" => Some(SagaStatus::Running),
            "completed" => Some(SagaStatus::Completed),
            "compensating" => Some(SagaStatus::Compensating),
            "compensated" => Some(SagaStatus::Compensated),
            "failed" => Some(SagaStatus::Failed),
            "timed_out" => Some(SagaStatus::TimedOut),
            "paused" => Some(SagaStatus::Paused),
            _ => None,
        }
    }
}

/// Status of an individual Saga step
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum SagaStepStatus {
    Pending,
    Running,
    Completed,
    Failed,
    Compensating,
    Compensated,
    Skipped,
}

impl SagaStepStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            SagaStepStatus::Pending => "pending",
            SagaStepStatus::Running => "running",
            SagaStepStatus::Completed => "completed",
            SagaStepStatus::Failed => "failed",
            SagaStepStatus::Compensating => "compensating",
            SagaStepStatus::Compensated => "compensated",
            SagaStepStatus::Skipped => "skipped",
        }
    }
}

/// A single step in a Saga definition
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaStepDefinition {
    pub step_index: u32,
    pub step_name: String,
    pub description: String,
    pub action: String,           // Action to execute
    pub compensating_action: String, // Rollback action if later steps fail
    pub is_critical: bool,        // If true, failure triggers compensation; if false, failure is logged and saga continues
    pub timeout_ms: u32,          // Step timeout in milliseconds
    pub retry_count: u32,         // Number of retries on failure
    pub requires_external_input: bool, // If true, saga pauses at this step
}

/// A Saga definition (template) for a subscription lifecycle operation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaDefinition {
    pub saga_type: SagaType,
    pub version: String,
    pub description: String,
    pub steps: Vec<SagaStepDefinition>,
    pub timeout_ms: u32,           // Total saga timeout
    pub max_retries: u32,          // Max retries for the entire saga
    pub payment_currency: String,
    pub payment_network: String,
}

/// Execution record for a step within a running saga
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaStepExecution {
    pub step_index: u32,
    pub step_name: String,
    pub status: SagaStepStatus,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub error_message: Option<String>,
    pub input_data: Option<String>,    // JSON input
    pub output_data: Option<String>,   // JSON output
    pub compensation_started_at: Option<String>,
    pub compensation_completed_at: Option<String>,
    pub compensation_error: Option<String>,
    pub retry_count: u32,
}

/// A running or completed Saga execution
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SagaExecution {
    pub execution_id: String,
    pub saga_type: SagaType,
    pub status: SagaStatus,
    pub tenant_id: String,
    pub subscription_id: Option<String>,
    pub steps: Vec<SagaStepExecution>,
    pub current_step_index: u32,
    pub started_at: String,
    pub completed_at: Option<String>,
    pub error_message: Option<String>,
    pub compensation_reason: Option<String>,
    pub metadata: Option<String>,     // JSON: arbitrary metadata
    pub payment_currency: String,
    pub payment_network: String,
}

// ═══════════════════════════════════════════════════════════════════════════
// Saga Definitions (Templates)
// ═══════════════════════════════════════════════════════════════════════════

/// Get the Saga definition for Trial Creation
/// Steps: validate_email → validate_wallet → create_trial_record → setup_feature_gates → create_audit_log
pub fn trial_creation_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::TrialCreation,
        version: "1.0.0".to_string(),
        description: "Orchestrates the creation of a 14-day trial subscription for a new user. All users MUST start with trial.".to_string(),
        steps: vec![
            SagaStepDefinition {
                step_index: 0,
                step_name: "validate_email".to_string(),
                description: "Validate user email and check for existing trials".to_string(),
                action: "validate_email_uniqueness".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 1,
                step_name: "validate_wallet".to_string(),
                description: "Validate the TRC20 wallet address format".to_string(),
                action: "validate_trc20_address".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 3000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 2,
                step_name: "create_trial_record".to_string(),
                description: "Create the trial subscription record in the database".to_string(),
                action: "db_create_subscription".to_string(),
                compensating_action: "db_delete_subscription".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 3,
                step_name: "setup_feature_gates".to_string(),
                description: "Initialize feature gate access for Business tier (trial)".to_string(),
                action: "initialize_feature_gates".to_string(),
                compensating_action: "revoke_feature_gates".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 4,
                step_name: "create_audit_log".to_string(),
                description: "Create audit log entry for trial creation".to_string(),
                action: "create_audit_entry".to_string(),
                compensating_action: "mark_audit_as_rolled_back".to_string(),
                is_critical: false,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
        ],
        timeout_ms: 60000,
        max_retries: 1,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Trial → Paid Conversion
/// Steps: validate_trial → validate_wallet → calculate_pricing → create_payment_request → update_subscription → update_feature_gates → create_audit_log
pub fn trial_conversion_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::TrialConversion,
        version: "1.0.0".to_string(),
        description: "Orchestrates converting a trial subscription to a paid tier with USDT TRC20 payment.".to_string(),
        steps: vec![
            SagaStepDefinition {
                step_index: 0,
                step_name: "validate_trial_active".to_string(),
                description: "Verify the trial subscription exists and is in trial status".to_string(),
                action: "validate_subscription_status".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 1,
                step_name: "validate_wallet_address".to_string(),
                description: "Validate the payer TRC20 wallet address".to_string(),
                action: "validate_trc20_address".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 3000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 2,
                step_name: "calculate_pricing".to_string(),
                description: "Calculate the first payment amount (monthly + setup fee)".to_string(),
                action: "calculate_subscription_pricing".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 3000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 3,
                step_name: "create_payment_request".to_string(),
                description: "Create a manual USDT TRC20 payment request record".to_string(),
                action: "db_create_payment_request".to_string(),
                compensating_action: "db_delete_payment_request".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 4,
                step_name: "update_subscription_record".to_string(),
                description: "Update subscription tier and status to paid".to_string(),
                action: "db_update_subscription".to_string(),
                compensating_action: "db_revert_subscription_to_trial".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 5,
                step_name: "update_feature_gates".to_string(),
                description: "Update feature gates for the new paid tier".to_string(),
                action: "update_feature_gates_for_tier".to_string(),
                compensating_action: "revert_feature_gates_to_trial".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 6,
                step_name: "create_conversion_audit".to_string(),
                description: "Create audit log for trial-to-paid conversion".to_string(),
                action: "create_audit_entry".to_string(),
                compensating_action: "mark_audit_as_rolled_back".to_string(),
                is_critical: false,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
        ],
        timeout_ms: 60000,
        max_retries: 1,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Payment Verification
/// Steps: validate_tx_hash → check_payment_uniqueness → create_payment_record → update_subscription_status → create_audit_log
pub fn payment_verification_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::PaymentVerification,
        version: "1.0.0".to_string(),
        description: "Orchestrates manual/semi-manual verification of a USDT TRC20 payment.".to_string(),
        steps: vec![
            SagaStepDefinition {
                step_index: 0,
                step_name: "validate_tx_hash".to_string(),
                description: "Validate the TRC20 transaction hash format (64 hex chars)".to_string(),
                action: "validate_trc20_tx_hash".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 3000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 1,
                step_name: "check_payment_uniqueness".to_string(),
                description: "Ensure this tx_hash hasn't been used before (double-spend prevention)".to_string(),
                action: "check_tx_hash_uniqueness".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 2,
                step_name: "create_payment_record".to_string(),
                description: "Create the payment record in the database with awaiting_confirmation status".to_string(),
                action: "db_create_payment".to_string(),
                compensating_action: "db_delete_payment".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 3,
                step_name: "update_subscription_status".to_string(),
                description: "Update subscription status to pending_payment or active".to_string(),
                action: "db_update_subscription_status".to_string(),
                compensating_action: "db_revert_subscription_status".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 4,
                step_name: "await_admin_confirmation".to_string(),
                description: "Wait for admin to manually confirm the USDT TRC20 payment".to_string(),
                action: "await_admin_confirmation".to_string(),
                compensating_action: "mark_payment_as_expired".to_string(),
                is_critical: true,
                timeout_ms: 86400000, // 24 hours for manual confirmation
                retry_count: 0,
                requires_external_input: true,
            },
            SagaStepDefinition {
                step_index: 5,
                step_name: "finalize_payment".to_string(),
                description: "Finalize payment after admin confirmation, set subscription to active".to_string(),
                action: "finalize_payment_confirmation".to_string(),
                compensating_action: "revert_payment_to_awaiting".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 6,
                step_name: "create_payment_audit".to_string(),
                description: "Create audit log for the payment verification".to_string(),
                action: "create_audit_entry".to_string(),
                compensating_action: "mark_audit_as_rolled_back".to_string(),
                is_critical: false,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
        ],
        timeout_ms: 172800000, // 48 hours total
        max_retries: 1,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Subscription Cancellation
/// Steps: validate_cancellation → update_subscription_status → revoke_feature_gates → process_refund_if_applicable → create_audit_log
pub fn cancellation_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::Cancellation,
        version: "1.0.0".to_string(),
        description: "Orchestrates subscription cancellation with feature revocation and optional refund.".to_string(),
        steps: vec![
            SagaStepDefinition {
                step_index: 0,
                step_name: "validate_cancellation".to_string(),
                description: "Validate that the subscription can be cancelled".to_string(),
                action: "validate_subscription_cancellable".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 1,
                step_name: "update_subscription_cancelled".to_string(),
                description: "Update subscription status to cancelled in database".to_string(),
                action: "db_cancel_subscription".to_string(),
                compensating_action: "db_reactivate_subscription".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 2,
                step_name: "revoke_feature_gates".to_string(),
                description: "Revoke all feature gate access for the tenant".to_string(),
                action: "revoke_all_feature_gates".to_string(),
                compensating_action: "restore_feature_gates".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 3,
                step_name: "process_refund_if_applicable".to_string(),
                description: "Process USDT TRC20 refund if applicable (manual admin process)".to_string(),
                action: "initiate_refund_process".to_string(),
                compensating_action: "cancel_refund_process".to_string(),
                is_critical: false,
                timeout_ms: 30000,
                retry_count: 1,
                requires_external_input: true,
            },
            SagaStepDefinition {
                step_index: 4,
                step_name: "create_cancellation_audit".to_string(),
                description: "Create audit log for the cancellation".to_string(),
                action: "create_audit_entry".to_string(),
                compensating_action: "mark_audit_as_rolled_back".to_string(),
                is_critical: false,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
        ],
        timeout_ms: 120000,
        max_retries: 1,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Subscription Renewal
pub fn renewal_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::Renewal,
        version: "1.0.0".to_string(),
        description: "Orchestrates subscription renewal with payment verification and usage reset.".to_string(),
        steps: vec![
            SagaStepDefinition {
                step_index: 0,
                step_name: "validate_renewal".to_string(),
                description: "Validate that the subscription is eligible for renewal".to_string(),
                action: "validate_subscription_renewable".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 1,
                step_name: "create_renewal_payment_request".to_string(),
                description: "Create payment request for the renewal amount".to_string(),
                action: "db_create_payment_request".to_string(),
                compensating_action: "db_delete_payment_request".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 2,
                step_name: "await_payment_confirmation".to_string(),
                description: "Wait for admin to confirm USDT TRC20 renewal payment".to_string(),
                action: "await_admin_confirmation".to_string(),
                compensating_action: "mark_payment_as_expired".to_string(),
                is_critical: true,
                timeout_ms: 86400000,
                retry_count: 0,
                requires_external_input: true,
            },
            SagaStepDefinition {
                step_index: 3,
                step_name: "extend_subscription_period".to_string(),
                description: "Extend the subscription period by 30 days".to_string(),
                action: "db_extend_subscription_period".to_string(),
                compensating_action: "db_revert_subscription_period".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 4,
                step_name: "reset_usage_records".to_string(),
                description: "Reset usage counters for the new billing period".to_string(),
                action: "db_reset_usage_records".to_string(),
                compensating_action: "db_restore_usage_records".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 5,
                step_name: "create_renewal_audit".to_string(),
                description: "Create audit log for the renewal".to_string(),
                action: "create_audit_entry".to_string(),
                compensating_action: "mark_audit_as_rolled_back".to_string(),
                is_critical: false,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
        ],
        timeout_ms: 172800000,
        max_retries: 1,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Tier Upgrade
pub fn upgrade_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::Upgrade,
        version: "1.0.0".to_string(),
        description: "Orchestrates tier upgrade with proration calculation and feature activation.".to_string(),
        steps: vec![
            SagaStepDefinition {
                step_index: 0,
                step_name: "validate_upgrade".to_string(),
                description: "Validate that the upgrade is valid (new tier > current tier)".to_string(),
                action: "validate_upgrade_path".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 1,
                step_name: "calculate_proration".to_string(),
                description: "Calculate prorated amount for the upgrade".to_string(),
                action: "calculate_proration_amount".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 2,
                step_name: "create_upgrade_payment_request".to_string(),
                description: "Create payment request for the prorated upgrade amount".to_string(),
                action: "db_create_payment_request".to_string(),
                compensating_action: "db_delete_payment_request".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 3,
                step_name: "await_payment_confirmation".to_string(),
                description: "Wait for admin to confirm USDT TRC20 upgrade payment".to_string(),
                action: "await_admin_confirmation".to_string(),
                compensating_action: "mark_payment_as_expired".to_string(),
                is_critical: true,
                timeout_ms: 86400000,
                retry_count: 0,
                requires_external_input: true,
            },
            SagaStepDefinition {
                step_index: 4,
                step_name: "update_subscription_tier".to_string(),
                description: "Update subscription to the new tier".to_string(),
                action: "db_update_subscription_tier".to_string(),
                compensating_action: "db_revert_subscription_tier".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 5,
                step_name: "activate_new_features".to_string(),
                description: "Activate features available in the new tier".to_string(),
                action: "update_feature_gates_for_tier".to_string(),
                compensating_action: "revert_feature_gates_to_previous_tier".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 6,
                step_name: "create_upgrade_audit".to_string(),
                description: "Create audit log for the upgrade".to_string(),
                action: "create_audit_entry".to_string(),
                compensating_action: "mark_audit_as_rolled_back".to_string(),
                is_critical: false,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
        ],
        timeout_ms: 172800000,
        max_retries: 1,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Tier Downgrade
pub fn downgrade_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::Downgrade,
        version: "1.0.0".to_string(),
        description: "Orchestrates tier downgrade with feature revocation and proration credit.".to_string(),
        steps: vec![
            SagaStepDefinition {
                step_index: 0,
                step_name: "validate_downgrade".to_string(),
                description: "Validate that the downgrade is valid (new tier < current tier)".to_string(),
                action: "validate_downgrade_path".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 1,
                step_name: "identify_revocable_features".to_string(),
                description: "Identify features that will be revoked in the lower tier".to_string(),
                action: "identify_features_to_revoke".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 2,
                step_name: "calculate_proration_credit".to_string(),
                description: "Calculate prorated credit for the downgrade".to_string(),
                action: "calculate_proration_credit".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 3,
                step_name: "update_subscription_tier".to_string(),
                description: "Update subscription to the lower tier".to_string(),
                action: "db_update_subscription_tier".to_string(),
                compensating_action: "db_revert_subscription_tier".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 4,
                step_name: "revoke_features".to_string(),
                description: "Revoke features not available in the lower tier".to_string(),
                action: "revoke_features_for_downgrade".to_string(),
                compensating_action: "restore_revoked_features".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 5,
                step_name: "create_downgrade_audit".to_string(),
                description: "Create audit log for the downgrade".to_string(),
                action: "create_audit_entry".to_string(),
                compensating_action: "mark_audit_as_rolled_back".to_string(),
                is_critical: false,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
        ],
        timeout_ms: 120000,
        max_retries: 1,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
    }
}

/// Get the Saga definition for Subscription Reactivation
pub fn reactivation_saga() -> SagaDefinition {
    SagaDefinition {
        saga_type: SagaType::Reactivation,
        version: "1.0.0".to_string(),
        description: "Orchestrates reactivation of a cancelled subscription.".to_string(),
        steps: vec![
            SagaStepDefinition {
                step_index: 0,
                step_name: "validate_reactivation".to_string(),
                description: "Validate that the subscription can be reactivated".to_string(),
                action: "validate_subscription_reactivatable".to_string(),
                compensating_action: "none".to_string(),
                is_critical: true,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 1,
                step_name: "create_reactivation_payment".to_string(),
                description: "Create payment request for reactivation".to_string(),
                action: "db_create_payment_request".to_string(),
                compensating_action: "db_delete_payment_request".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 2,
                step_name: "await_payment_confirmation".to_string(),
                description: "Wait for admin to confirm USDT TRC20 reactivation payment".to_string(),
                action: "await_admin_confirmation".to_string(),
                compensating_action: "mark_payment_as_expired".to_string(),
                is_critical: true,
                timeout_ms: 86400000,
                retry_count: 0,
                requires_external_input: true,
            },
            SagaStepDefinition {
                step_index: 3,
                step_name: "reactivate_subscription".to_string(),
                description: "Update subscription status back to active".to_string(),
                action: "db_reactivate_subscription".to_string(),
                compensating_action: "db_cancel_subscription".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 4,
                step_name: "restore_feature_gates".to_string(),
                description: "Restore feature gate access for the tier".to_string(),
                action: "restore_feature_gates".to_string(),
                compensating_action: "revoke_all_feature_gates".to_string(),
                is_critical: true,
                timeout_ms: 10000,
                retry_count: 2,
                requires_external_input: false,
            },
            SagaStepDefinition {
                step_index: 5,
                step_name: "create_reactivation_audit".to_string(),
                description: "Create audit log for the reactivation".to_string(),
                action: "create_audit_entry".to_string(),
                compensating_action: "mark_audit_as_rolled_back".to_string(),
                is_critical: false,
                timeout_ms: 5000,
                retry_count: 1,
                requires_external_input: false,
            },
        ],
        timeout_ms: 172800000,
        max_retries: 1,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
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

/// Calculate proration amount for an upgrade/downgrade
pub fn calculate_proration(
    current_tier: SubscriptionTier,
    new_tier: SubscriptionTier,
    days_remaining: u32,
    days_in_period: u32,
) -> ProrationResult {
    let current_monthly = current_tier.monthly_price_usdt();
    let new_monthly = new_tier.monthly_price_usdt();
    let daily_current = current_monthly / 30.0;
    let daily_new = new_monthly / 30.0;

    let remaining_fraction = if days_in_period > 0 { days_remaining as f64 / days_in_period as f64 } else { 0.0 };

    let credit = daily_current * days_remaining as f64;
    let charge = daily_new * days_remaining as f64;
    let net_amount = charge - credit;

    ProrationResult {
        current_tier: current_tier.as_str().to_string(),
        new_tier: new_tier.as_str().to_string(),
        current_monthly_usdt: current_monthly,
        new_monthly_usdt: new_monthly,
        days_remaining,
        days_in_period,
        remaining_fraction,
        credit_usdt: credit,
        charge_usdt: charge,
        net_amount_usdt: net_amount,
        is_upgrade: net_amount > 0.0,
        payment_currency: "USDT".to_string(),
        payment_network: "TRC20".to_string(),
    }
}

/// Result of a proration calculation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProrationResult {
    pub current_tier: String,
    pub new_tier: String,
    pub current_monthly_usdt: f64,
    pub new_monthly_usdt: f64,
    pub days_remaining: u32,
    pub days_in_period: u32,
    pub remaining_fraction: f64,
    pub credit_usdt: f64,
    pub charge_usdt: f64,
    pub net_amount_usdt: f64,
    pub is_upgrade: bool,
    pub payment_currency: String,
    pub payment_network: String,
}

/// Validate an upgrade path (must go from lower to higher tier)
pub fn validate_upgrade_path(current: SubscriptionTier, new: SubscriptionTier) -> Result<(), String> {
    let current_rank = tier_rank(current);
    let new_rank = tier_rank(new);

    if new_rank <= current_rank {
        return Err(format!("Invalid upgrade: {} → {}. New tier must be higher than current.", current.display_name(), new.display_name()));
    }
    Ok(())
}

/// Validate a downgrade path (must go from higher to lower tier)
pub fn validate_downgrade_path(current: SubscriptionTier, new: SubscriptionTier) -> Result<(), String> {
    let current_rank = tier_rank(current);
    let new_rank = tier_rank(new);

    if new_rank >= current_rank {
        return Err(format!("Invalid downgrade: {} → {}. New tier must be lower than current.", current.display_name(), new.display_name()));
    }
    Ok(())
}

/// Tier ranking for upgrade/downgrade validation
fn tier_rank(tier: SubscriptionTier) -> u32 {
    match tier {
        SubscriptionTier::Starter => 1,
        SubscriptionTier::Business => 2,
        SubscriptionTier::Enterprise => 3,
        SubscriptionTier::OnPremiseEnterprise => 4,
        SubscriptionTier::Trial => 0, // Trial is below all paid tiers
    }
}

// ─── Internal Helpers (duplicated from lib.rs to avoid circular imports) ──

fn sha256_short(input: &str) -> String {
    use sha2::{Sha256, Digest};
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    format!("{:x}", hasher.finalize())[..12].to_string()
}

fn chrono_now_iso() -> String {
    chrono::Utc::now().to_rfc3339()
}
