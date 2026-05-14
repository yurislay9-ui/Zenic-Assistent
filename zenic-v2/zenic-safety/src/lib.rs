//! # zenic-safety
//!
//! Extended safety gate with domain-specific rules, compliance validation,
//! and sensitivity escalation for Zenic-Agents (Phase D).
//!
//! This crate provides:
//! - [`DomainSafetyGate`] — 4-layer safety validation pipeline
//! - [`NicheCategory`] — 7 niche domain categories
//! - [`DataSensitivity`] — 4 sensitivity levels (low/medium/high/critical)
//! - [`ComplianceEngine`] — Regulatory compliance checker (HIPAA, PCI-DSS, GDPR, etc.)
//! - [`DomainRuleSet`] — 35 domain-specific safety rules (5 per NicheCategory)
//! - [`SafetyVerdict`] — Verdict with escalation semantics
//!
//! # Safety Invariants
//!
//! 1. Domain rules can only ESCALATE verdicts, never downgrade.
//! 2. Compliance failures for critical violations result in DENY.
//! 3. If the base gate returns DENY, domain gate CANNOT override.
//! 4. All logic is deterministic — no AI, no randomness.

pub mod categories;
pub mod compliance;
pub mod domain_rules;
pub mod engine;
pub mod errors;
pub mod sensitivity;
pub mod verdict;

// Convenience re-exports.
pub use categories::NicheCategory;
pub use compliance::{ComplianceEngine, ComplianceResult, ComplianceStandard};
pub use domain_rules::{DomainRule, DomainRuleSet};
pub use engine::DomainSafetyGate;
pub use errors::SafetyError;
pub use sensitivity::DataSensitivity;
pub use verdict::SafetyVerdict;
