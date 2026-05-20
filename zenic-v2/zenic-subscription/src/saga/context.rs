//! Saga context: shared mutable state for saga execution.

use std::collections::HashMap;

use zenic_proto::TenantId;

use crate::types::{SubscriptionTierName, SubscriptionStatus};

// ---------------------------------------------------------------------------
// SagaStepResult
// ---------------------------------------------------------------------------

/// Result of executing a single saga step.
#[derive(Debug, Clone)]
pub struct SagaStepResult {
    /// Step name.
    pub step_name: String,
    /// Whether the step succeeded.
    pub success: bool,
    /// Optional result data.
    pub data: HashMap<String, String>,
    /// Duration in milliseconds.
    pub duration_ms: u64,
}

impl SagaStepResult {
    /// Creates a successful step result.
    pub fn success(step_name: &str) -> Self {
        Self {
            step_name: step_name.to_string(),
            success: true,
            data: HashMap::new(),
            duration_ms: 0,
        }
    }

    /// Creates a successful step result with data.
    pub fn success_with_data(step_name: &str, data: HashMap<String, String>) -> Self {
        Self {
            step_name: step_name.to_string(),
            success: true,
            data,
            duration_ms: 0,
        }
    }

    /// Adds a key-value pair to the result data.
    pub fn with_data(mut self, key: &str, value: &str) -> Self {
        self.data.insert(key.to_string(), value.to_string());
        self
    }

    /// Sets the duration.
    pub fn with_duration(mut self, ms: u64) -> Self {
        self.duration_ms = ms;
        self
    }
}

// ---------------------------------------------------------------------------
// SagaContext
// ---------------------------------------------------------------------------

/// Shared mutable context for a saga execution.
///
/// Tracks the state of the saga, including completed steps,
/// compensation state, and any data produced by steps.
pub struct SagaContext {
    /// The tenant this saga is operating on.
    pub tenant_id: TenantId,
    /// Current subscription tier (may change during upgrade saga).
    pub current_tier: SubscriptionTierName,
    /// Target subscription tier (for upgrade/downgrade).
    pub target_tier: Option<SubscriptionTierName>,
    /// Current subscription status.
    pub subscription_status: SubscriptionStatus,
    /// The name of the currently executing step.
    pub current_step: Option<String>,
    /// Steps that have completed successfully.
    pub completed_steps: Vec<String>,
    /// Steps that have been compensated.
    pub compensated_steps: Vec<String>,
    /// Whether the saga has failed.
    pub saga_failed: bool,
    /// Whether the saga has completed successfully.
    pub saga_completed: bool,
    /// The step that failed (if any).
    pub failed_step: Option<String>,
    /// The reason for failure (if any).
    pub failure_reason: Option<String>,
    /// Shared data produced by steps (key-value store).
    pub data: HashMap<String, String>,
    /// Amount in USDT (for payment sagas).
    pub amount_usdt: Option<u64>,
    /// USDT TRC20 transaction hash (for payment sagas).
    pub tx_hash: Option<String>,
    /// Wallet address (for payment sagas).
    pub wallet_address: Option<String>,
    /// Admin who verified (for manual payments).
    pub verified_by: Option<String>,
    /// Number of days remaining in billing period (for proration).
    pub days_remaining: Option<u32>,
    /// Number of days in the billing period.
    pub days_in_period: Option<u32>,
    /// Prorated amount (for upgrade sagas).
    pub proration_amount: Option<u64>,
}

impl SagaContext {
    /// Creates a new saga context for a tenant.
    pub fn new(tenant_id: TenantId, current_tier: SubscriptionTierName) -> Self {
        Self {
            tenant_id,
            current_tier,
            target_tier: None,
            subscription_status: SubscriptionStatus::Trial,
            current_step: None,
            completed_steps: Vec::new(),
            compensated_steps: Vec::new(),
            saga_failed: false,
            saga_completed: false,
            failed_step: None,
            failure_reason: None,
            data: HashMap::new(),
            amount_usdt: None,
            tx_hash: None,
            wallet_address: None,
            verified_by: None,
            days_remaining: None,
            days_in_period: None,
            proration_amount: None,
        }
    }

    /// Sets a data value.
    pub fn set_data(&mut self, key: &str, value: &str) {
        self.data.insert(key.to_string(), value.to_string());
    }

    /// Gets a data value.
    pub fn get_data(&self, key: &str) -> Option<&str> {
        self.data.get(key).map(|s| s.as_str())
    }

    /// Whether a step has completed.
    pub fn is_step_completed(&self, step_name: &str) -> bool {
        self.completed_steps.iter().any(|s| s == step_name)
    }

    /// Whether a step has been compensated.
    pub fn is_step_compensated(&self, step_name: &str) -> bool {
        self.compensated_steps.iter().any(|s| s == step_name)
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn saga_step_result_success() {
        let result = SagaStepResult::success("test_step");
        assert_eq!(result.step_name, "test_step");
        assert!(result.success);
    }

    #[test]
    fn saga_step_result_with_data() {
        let result = SagaStepResult::success("test_step")
            .with_data("key", "value")
            .with_duration(100);
        assert_eq!(result.data.get("key"), Some(&"value".to_string()));
        assert_eq!(result.duration_ms, 100);
    }

    #[test]
    fn saga_context_new() {
        let ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Starter);
        assert_eq!(ctx.current_tier, SubscriptionTierName::Starter);
        assert!(ctx.completed_steps.is_empty());
        assert!(!ctx.saga_failed);
    }

    #[test]
    fn saga_context_data() {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Starter);
        ctx.set_data("key", "value");
        assert_eq!(ctx.get_data("key"), Some("value"));
    }

    #[test]
    fn saga_context_step_tracking() {
        let mut ctx = SagaContext::new(TenantId::new(), SubscriptionTierName::Starter);
        ctx.completed_steps.push("step1".to_string());
        assert!(ctx.is_step_completed("step1"));
        assert!(!ctx.is_step_completed("step2"));
    }
}
