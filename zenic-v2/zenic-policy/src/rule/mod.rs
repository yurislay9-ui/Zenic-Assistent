//! Policy rules: allow/deny rules with conditions and priorities.
//!
//! A [`PolicyRule`] defines whether a specific action on a resource
//! is allowed or denied, optionally subject to conditions. Rules are
//! collected in a [`RuleSet`] and evaluated in priority order during
//! policy evaluation.

pub mod definition;
pub mod evaluator;
pub mod types;

// Re-export all public API so that `rule::PolicyRule` etc.
// continue to work without changes in the parent lib.rs.
pub use types::{RuleCondition, RuleEffect};
pub use definition::PolicyRule;
pub use evaluator::RuleSet;
