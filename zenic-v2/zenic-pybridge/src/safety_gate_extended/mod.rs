//! Safety Gate Extended — Domain-specific security rules + compliance for Zenic-Agents (Phase D).
//!
//! Extends the base SafetyGate (10 generic rules) with:
//! - 35 domain-specific safety rules scoped by NicheCategory
//! - Compliance validation engines (HIPAA, PCI-DSS, GDPR, SOX, AML/KYC)
//! - Data sensitivity escalation logic
//! - Domain-aware rate limiting
//!
//! # TODO: Deduplicate with zenic-safety crate
//!
//! This module duplicates logic already implemented in the `zenic-safety` crate
//! (zenic-v2/zenic-safety/). The `zenic-safety` crate has:
//! - `DomainSafetyGate` with the same 4-layer pipeline
//! - `DomainRuleSet` with the same 35 domain rules
//! - `ComplianceEngine` with the same compliance standards
//! - `DataSensitivity` with the same escalation logic
//!
//! `zenic-pybridge` now depends on `zenic-safety` (added to Cargo.toml).
//! Next step: refactor this module to delegate to `zenic-safety::DomainSafetyGate`
//! and only add the PyO3 `#[pyclass]`/`#[pyfunction]` wrappers here,
//! eliminating the ~700 lines of duplicated domain rules and compliance logic.
//!
//! # Architecture
//!
//! The extended gate layers on top of the base gate:
//!
//! 1. Base SafetyGate: 10 generic rules (SQL injection, DROP, financial, etc.)
//! 2. Domain Rules: 35 niche-specific rules (5 per NicheCategory)
//! 3. Compliance Gate: Regulatory validation per standard
//! 4. Sensitivity Escalation: Auto-escalate verdict based on data_sensitivity
//!
//! # INVARIANT
//!
//! If the base gate returns DENY, the extended gate CANNOT override it.
//! Domain rules can only ESCALATE verdicts, never downgrade them.
//! Compliance failures always result in DENY for the violating action.
//!
//! # PyO3 Exposed Types
//!
//! - `DomainSafetyRule` — a safety rule scoped to a NicheCategory
//! - `ComplianceStandard` — regulatory compliance standard enum
//! - `ComplianceCheckResult` — result of a compliance validation
//! - `DomainSafetyCheckResult` — extended safety check result with domain info
//!
//! # PyO3 Exposed Functions
//!
//! - `safety_validate_extended(action_type, config, category_str, sensitivity_str)` — full validation pipeline
//! - `safety_validate_domain(action_type, config, niche_category)` — domain-specific validation
//! - `safety_check_compliance(config, standard)` — compliance validation
//! - `safety_check_compliance_batch(config, standards)` — batch compliance check
//! - `safety_get_domain_rules(niche_category)` — get rules for a domain
//! - `safety_escalate_verdict(base_verdict_str, sensitivity_str)` — sensitivity escalation
//! - `safety_get_compliance_for_category(niche_category)` — compliance standards for domain

mod types;
mod domain_rules;
mod helpers;
mod api;

// Re-export all public types and functions so `crate::safety_gate_extended::*` still works.
pub use types::{
    ComplianceStandard,
    DomainSafetyRule,
    ComplianceCheckResult,
    DomainSafetyCheckResult,
};

pub use api::{
    safety_validate_extended,
    safety_validate_domain,
    safety_check_compliance,
    safety_check_compliance_batch,
    safety_get_domain_rules,
    safety_escalate_verdict,
    safety_get_compliance_for_category,
};
