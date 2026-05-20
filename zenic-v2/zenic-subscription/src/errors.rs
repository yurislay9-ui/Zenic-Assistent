//! Subscription and payment error types.

use thiserror::Error;
use zenic_proto::PaymentId;
use zenic_proto::SubscriptionId;
use zenic_proto::TrialId;

/// Errors that can occur during subscription operations.
#[derive(Debug, Error)]
pub enum SubscriptionError {
    /// A subscription was not found.
    #[error("subscription not found: {0}")]
    SubscriptionNotFound(SubscriptionId),

    /// A payment was not found.
    #[error("payment not found: {0}")]
    PaymentNotFound(PaymentId),

    /// A trial was not found.
    #[error("trial not found: {0}")]
    TrialNotFound(TrialId),

    /// The subscription is in an invalid state for the requested operation.
    #[error("invalid subscription state: cannot {action} while in {state}")]
    InvalidState {
        action: String,
        state: String,
    },

    /// A payment verification failed.
    #[error("payment verification failed: {reason}")]
    PaymentVerificationFailed {
        reason: String,
    },

    /// The USDT TRC20 transaction hash is invalid.
    #[error("invalid USDT TRC20 transaction hash: {0}")]
    InvalidTxHash(String),

    /// The wallet address is invalid.
    #[error("invalid wallet address: {0}")]
    InvalidWalletAddress(String),

    /// The payment amount does not match the expected amount.
    #[error("payment amount mismatch: expected {expected} USDT, got {actual} USDT")]
    PaymentAmountMismatch {
        expected: u64,
        actual: u64,
    },

    /// The trial has expired.
    #[error("trial expired at {expired_at_ms}")]
    TrialExpired {
        expired_at_ms: u64,
    },

    /// The subscription tier does not support the requested feature.
    #[error("feature '{feature}' not available in tier '{tier}'")]
    FeatureNotAvailable {
        feature: String,
        tier: String,
    },

    /// Usage limit exceeded for the current tier.
    #[error("usage limit exceeded: {usage_type} limit is {limit}, current is {current}")]
    UsageLimitExceeded {
        usage_type: String,
        limit: u64,
        current: u64,
    },

    /// A saga step failed and compensation was triggered.
    #[error("saga step '{step}' failed, compensation applied: {reason}")]
    SagaCompensated {
        step: String,
        reason: String,
    },

    /// A saga step failed and compensation also failed.
    #[error("saga step '{step}' failed and compensation also failed: {reason}")]
    SagaCompensationFailed {
        step: String,
        reason: String,
    },

    /// An invalid state transition was attempted.
    #[error("cannot transition subscription from {from} to {to}")]
    InvalidTransition {
        from: String,
        to: String,
    },

    /// Validation error.
    #[error("validation error: {0}")]
    Validation(String),

    /// A general subscription error.
    #[error("subscription error: {0}")]
    General(String),
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn subscription_not_found_display() {
        let id = SubscriptionId::new();
        let err = SubscriptionError::SubscriptionNotFound(id);
        let msg = err.to_string();
        assert!(msg.contains("subscription not found"));
    }

    #[test]
    fn payment_amount_mismatch_display() {
        let err = SubscriptionError::PaymentAmountMismatch {
            expected: 99,
            actual: 50,
        };
        let msg = err.to_string();
        assert!(msg.contains("99"));
        assert!(msg.contains("50"));
    }

    #[test]
    fn feature_not_available_display() {
        let err = SubscriptionError::FeatureNotAvailable {
            feature: "advanced_analytics".to_string(),
            tier: "starter".to_string(),
        };
        let msg = err.to_string();
        assert!(msg.contains("advanced_analytics"));
        assert!(msg.contains("starter"));
    }

    #[test]
    fn saga_compensated_display() {
        let err = SubscriptionError::SagaCompensated {
            step: "apply_subscription".to_string(),
            reason: "db error".to_string(),
        };
        let msg = err.to_string();
        assert!(msg.contains("apply_subscription"));
        assert!(msg.contains("compensation applied"));
    }
}
