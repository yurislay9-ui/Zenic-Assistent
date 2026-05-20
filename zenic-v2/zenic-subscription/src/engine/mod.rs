//! Subscription engine: main orchestrator for the subscription system.
//!
//! The [`SubscriptionEngine`] coordinates all subscription operations:
//! - Signup with 14-day trial
//! - USDT TRC20 payment processing
//! - Tier upgrades with proration
//! - Subscription cancellation and renewal
//! - Feature gate enforcement
//! - Usage metering
//!
//! All operations use the Saga pattern for reliability.

pub mod lifecycle;
pub mod queries;
pub mod types;

// Re-export the primary type so that `engine::SubscriptionEngine`
// continues to work without changes in the parent lib.rs.
pub use types::SubscriptionEngine;
