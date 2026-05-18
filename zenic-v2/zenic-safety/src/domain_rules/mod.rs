//! Domain-specific safety rules — 5 rules per NicheCategory = 35 total.
//!
//! Each rule is deterministic: regex-based pattern matching.
//! Domain rules can only ESCALATE verdicts, never downgrade.
//!
//! Sub-modules:
//! - [`types`] — DomainRule struct and Display impl
//! - [`loader`] — Rule builder functions (35 rules)
//! - [`evaluator`] — DomainRuleSet query/check + tests

pub mod evaluator;
pub mod loader;
pub mod types;

// Convenience re-exports — preserves the original public API surface.
pub use evaluator::DomainRuleSet;
pub use types::DomainRule;
