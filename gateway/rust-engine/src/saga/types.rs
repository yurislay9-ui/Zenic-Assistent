// ─── Saga Core Types ─────────────────────────────────────────────────────
// SagaType, SagaStatus, SagaStepStatus, SagaStepDefinition,
// SagaDefinition, SagaStepExecution, SagaExecution

use serde::{Deserialize, Serialize};

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
