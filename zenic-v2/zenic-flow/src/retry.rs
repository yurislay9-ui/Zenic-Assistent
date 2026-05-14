//! Retry policy with exponential backoff for durable workflows.
//!
//! Each workflow step can have its own retry policy, or inherit the
//! workflow's default. The backoff calculation is deterministic:
//! `delay = min(initial_delay * backoff_multiplier^(attempt-1), max_delay)`.

use serde::{Deserialize, Serialize};
use std::time::Duration;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Default maximum number of retries.
pub const DEFAULT_MAX_RETRIES: u32 = 3;

/// Default initial delay before the first retry (1 second).
pub const DEFAULT_INITIAL_DELAY_MS: u64 = 1000;

/// Default maximum delay cap (60 seconds).
pub const DEFAULT_MAX_DELAY_MS: u64 = 60_000;

/// Default backoff multiplier (2.0 = double each attempt).
pub const DEFAULT_BACKOFF_MULTIPLIER: f64 = 2.0;

// ---------------------------------------------------------------------------
// RetryPolicy
// ---------------------------------------------------------------------------

/// Policy for retrying a failed workflow step with exponential backoff.
///
/// The delay for attempt `n` (1-based) is calculated as:
/// `delay = min(initial_delay * backoff_multiplier^(n-1), max_delay)`
///
/// For example, with default settings:
/// - Attempt 1: 1s
/// - Attempt 2: 2s
/// - Attempt 3: 4s
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RetryPolicy {
    /// Maximum number of retry attempts (0 = no retries).
    pub max_retries: u32,
    /// Initial delay before the first retry, in milliseconds.
    pub initial_delay_ms: u64,
    /// Maximum delay cap, in milliseconds.
    pub max_delay_ms: u64,
    /// Multiplier applied to the delay after each attempt.
    pub backoff_multiplier: f64,
}

impl RetryPolicy {
    /// Creates a new retry policy with the given parameters.
    pub fn new(
        max_retries: u32,
        initial_delay_ms: u64,
        max_delay_ms: u64,
        backoff_multiplier: f64,
    ) -> Self {
        Self {
            max_retries,
            initial_delay_ms,
            max_delay_ms,
            backoff_multiplier,
        }
    }

    /// Creates a retry policy with no retries (fail immediately).
    pub fn no_retry() -> Self {
        Self {
            max_retries: 0,
            initial_delay_ms: 0,
            max_delay_ms: 0,
            backoff_multiplier: 1.0,
        }
    }

    /// Returns the default retry policy.
    pub fn default_policy() -> Self {
        Self {
            max_retries: DEFAULT_MAX_RETRIES,
            initial_delay_ms: DEFAULT_INITIAL_DELAY_MS,
            max_delay_ms: DEFAULT_MAX_DELAY_MS,
            backoff_multiplier: DEFAULT_BACKOFF_MULTIPLIER,
        }
    }

    /// Calculates the delay for a given attempt number (1-based).
    ///
    /// Returns `None` if the attempt exceeds `max_retries`.
    /// The formula is: `min(initial_delay * backoff_multiplier^(attempt-1), max_delay)`.
    pub fn delay_for_attempt(&self, attempt: u32) -> Option<Duration> {
        if attempt == 0 || attempt > self.max_retries {
            return None;
        }

        let exponent = (attempt - 1) as f64;
        let delay_ms = (self.initial_delay_ms as f64)
            * self.backoff_multiplier.powf(exponent);

        let capped_ms = delay_ms.min(self.max_delay_ms as f64);
        Some(Duration::from_millis(capped_ms as u64))
    }

    /// Whether retries are enabled (max_retries > 0).
    pub fn is_retry_enabled(&self) -> bool {
        self.max_retries > 0
    }

    /// Total number of attempts including the initial one.
    pub fn total_attempts(&self) -> u32 {
        self.max_retries + 1
    }

    /// Validates the retry policy for internal consistency.
    pub fn validate(&self) -> Result<(), String> {
        if self.backoff_multiplier < 1.0 {
            return Err(format!(
                "backoff_multiplier must be >= 1.0, got {}",
                self.backoff_multiplier
            ));
        }
        if self.max_delay_ms < self.initial_delay_ms && self.max_retries > 0 {
            return Err(format!(
                "max_delay_ms ({}) must be >= initial_delay_ms ({})",
                self.max_delay_ms, self.initial_delay_ms
            ));
        }
        Ok(())
    }
}

impl Default for RetryPolicy {
    fn default() -> Self {
        Self::default_policy()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_policy_values() {
        let policy = RetryPolicy::default();
        assert_eq!(policy.max_retries, DEFAULT_MAX_RETRIES);
        assert_eq!(policy.initial_delay_ms, DEFAULT_INITIAL_DELAY_MS);
        assert_eq!(policy.max_delay_ms, DEFAULT_MAX_DELAY_MS);
        assert!((policy.backoff_multiplier - DEFAULT_BACKOFF_MULTIPLIER).abs() < f64::EPSILON);
    }

    #[test]
    fn no_retry_policy() {
        let policy = RetryPolicy::no_retry();
        assert_eq!(policy.max_retries, 0);
        assert!(!policy.is_retry_enabled());
        assert_eq!(policy.total_attempts(), 1);
    }

    #[test]
    fn delay_for_attempt_basic() {
        let policy = RetryPolicy::new(3, 1000, 60_000, 2.0);
        // Attempt 1: 1000 * 2^0 = 1000
        assert_eq!(policy.delay_for_attempt(1), Some(Duration::from_millis(1000)));
        // Attempt 2: 1000 * 2^1 = 2000
        assert_eq!(policy.delay_for_attempt(2), Some(Duration::from_millis(2000)));
        // Attempt 3: 1000 * 2^2 = 4000
        assert_eq!(policy.delay_for_attempt(3), Some(Duration::from_millis(4000)));
    }

    #[test]
    fn delay_for_attempt_exceeds_max() {
        let policy = RetryPolicy::new(5, 1000, 5000, 2.0);
        // Attempt 4: 1000 * 2^3 = 8000, capped at 5000
        assert_eq!(policy.delay_for_attempt(4), Some(Duration::from_millis(5000)));
        // Attempt 5: 1000 * 2^4 = 16000, capped at 5000
        assert_eq!(policy.delay_for_attempt(5), Some(Duration::from_millis(5000)));
    }

    #[test]
    fn delay_for_attempt_out_of_range() {
        let policy = RetryPolicy::new(3, 1000, 60_000, 2.0);
        assert!(policy.delay_for_attempt(0).is_none());
        assert!(policy.delay_for_attempt(4).is_none());
    }

    #[test]
    fn delay_for_no_retry() {
        let policy = RetryPolicy::no_retry();
        assert!(policy.delay_for_attempt(1).is_none());
    }

    #[test]
    fn total_attempts() {
        let policy = RetryPolicy::new(3, 1000, 60_000, 2.0);
        assert_eq!(policy.total_attempts(), 4);
    }

    #[test]
    fn validate_valid_policy() {
        let policy = RetryPolicy::default();
        assert!(policy.validate().is_ok());
    }

    #[test]
    fn validate_backoff_below_one() {
        let policy = RetryPolicy::new(3, 1000, 60_000, 0.5);
        assert!(policy.validate().is_err());
    }

    #[test]
    fn validate_max_less_than_initial() {
        let policy = RetryPolicy::new(3, 5000, 1000, 2.0);
        assert!(policy.validate().is_err());
    }

    #[test]
    fn validate_max_less_than_initial_but_no_retries_is_ok() {
        let policy = RetryPolicy::new(0, 5000, 1000, 2.0);
        assert!(policy.validate().is_ok());
    }

    #[test]
    fn custom_new() {
        let policy = RetryPolicy::new(5, 500, 30_000, 1.5);
        assert_eq!(policy.max_retries, 5);
        assert_eq!(policy.initial_delay_ms, 500);
        assert_eq!(policy.max_delay_ms, 30_000);
        assert!((policy.backoff_multiplier - 1.5).abs() < f64::EPSILON);
    }
}
