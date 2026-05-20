//! Core subscription types: tiers, status, limits, add-ons.
//!
//! The subscription model has 5 tiers:
//! - **Starter**: $29/mo USDT TRC20
//! - **Business**: $99/mo USDT TRC20
//! - **Enterprise**: $299/mo USDT TRC20
//! - **On-Premise Enterprise**: $799/mo + $2,000 setup USDT TRC20
//!
//! All users get a **14-day trial** with full Business plan access.
//! All payments are **USDT TRC20 only**, manual or semi-manual processing.

pub mod billing;
pub mod core;
pub mod plan;

// Re-export all public items so that `crate::types::X` still resolves.
pub use billing::Subscription;
pub use core::{SubscriptionStatus, SubscriptionTierName, TierLimits};
pub use plan::{AddOn, AddOnId, SubscriptionTier};
