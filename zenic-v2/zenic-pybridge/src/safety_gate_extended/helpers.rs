//! Internal helper functions for the extended safety gate.
//!
//! - `can_escalate` — check if a domain rule can escalate the base verdict
//! - `escalate_by_sensitivity` — escalate verdict based on data sensitivity
//! - `parse_niche_category` — parse a NicheCategory from a string
//! - `config_to_searchable` — convert config dict to searchable string
//! - `validate_compliance` — validate an action against a compliance standard

use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::niche::NicheCategory;
use crate::safety_gate::SafetyVerdict;
use super::types::{ComplianceCheckResult, ComplianceStandard};

// ═══════════════════════════════════════════════════════════════
//  Verdict Escalation
// ═══════════════════════════════════════════════════════════════

/// Verdict escalation: determine if a domain rule can escalate the base verdict.
///
/// Escalation order: ALLOW < CONFIRM < APPROVE < DENY
/// A domain rule CAN escalate but CANNOT downgrade.
pub(crate) fn can_escalate(base: &SafetyVerdict, domain: &SafetyVerdict) -> bool {
    let base_level = match base {
        SafetyVerdict::Allow => 0,
        SafetyVerdict::Confirm => 1,
        SafetyVerdict::Approve => 2,
        SafetyVerdict::Deny => 3,
        SafetyVerdict::RateLimited => 3,
    };
    let domain_level = match domain {
        SafetyVerdict::Allow => 0,
        SafetyVerdict::Confirm => 1,
        SafetyVerdict::Approve => 2,
        SafetyVerdict::Deny => 3,
        SafetyVerdict::RateLimited => 3,
    };
    domain_level > base_level
}

/// Sensitivity escalation: escalate verdict based on data_sensitivity.
///
/// - critical: CONFIRM → APPROVE, APPROVE → DENY
/// - high: ALLOW → CONFIRM, CONFIRM → APPROVE
/// - medium: no escalation
/// - low: no escalation
pub(crate) fn escalate_by_sensitivity(verdict: &SafetyVerdict, sensitivity: &str) -> (SafetyVerdict, bool) {
    match sensitivity.to_lowercase().as_str() {
        "critical" => match verdict {
            SafetyVerdict::Allow => (SafetyVerdict::Confirm, true),
            SafetyVerdict::Confirm => (SafetyVerdict::Approve, true),
            SafetyVerdict::Approve => (SafetyVerdict::Deny, true),
            _ => (verdict.clone(), false),
        },
        "high" => match verdict {
            SafetyVerdict::Allow => (SafetyVerdict::Confirm, true),
            SafetyVerdict::Confirm => (SafetyVerdict::Approve, true),
            _ => (verdict.clone(), false),
        },
        _ => (verdict.clone(), false),
    }
}

// ═══════════════════════════════════════════════════════════════
//  Category Parsing
// ═══════════════════════════════════════════════════════════════

/// Parse a NicheCategory from a string.
pub(crate) fn parse_niche_category(s: &str) -> Option<NicheCategory> {
    match s.trim().to_lowercase().as_str() {
        "ai_data" => Some(NicheCategory::AiData),
        "fintech" => Some(NicheCategory::FinTech),
        "healthtech" => Some(NicheCategory::HealthTech),
        "greentech" => Some(NicheCategory::GreenTech),
        "edtech" => Some(NicheCategory::EdTech),
        "proptech" => Some(NicheCategory::PropTech),
        "legaltech" => Some(NicheCategory::LegalTech),
        _ => None,
    }
}

// ═══════════════════════════════════════════════════════════════
//  Config Helpers
// ═══════════════════════════════════════════════════════════════

/// Convert config dict to searchable string (reuses base gate logic).
pub(crate) fn config_to_searchable(action_type: &str, config: &Bound<'_, PyDict>) -> PyResult<String> {
    let mut parts: Vec<String> = vec![action_type.to_string()];
    for (_, value) in config.iter() {
        if let Ok(s) = value.extract::<String>() {
            parts.push(s);
        } else {
            parts.push(value.str()?.extract::<String>()?);
        }
    }
    Ok(parts.join(" "))
}

// ═══════════════════════════════════════════════════════════════
//  Compliance Validation
// ═══════════════════════════════════════════════════════════════

/// Validate an action against a specific compliance standard.
pub(crate) fn validate_compliance(
    config: &Bound<'_, PyDict>,
    standard: ComplianceStandard,
    _py: Python<'_>,
) -> ComplianceCheckResult {
    let mut violations: Vec<String> = Vec::new();
    let mut recommendations: Vec<String> = Vec::new();
    let mut risk_level = "low".to_string();

    // Get searchable config values
    let config_str = match config_to_searchable("", config) {
        Ok(s) => s.to_lowercase(),
        Err(_) => String::new(),
    };

    match standard {
        ComplianceStandard::Hipaa => {
            // Check for PHI handling without encryption
            if config_str.contains("phi") || config_str.contains("patient") || config_str.contains("medical") {
                let encrypted = config.get_item("encrypted")
                    .ok().flatten()
                    .and_then(|v| v.extract::<bool>().ok())
                    .unwrap_or(false);
                if !encrypted {
                    violations.push("PHI data operation without encryption flag".to_string());
                    recommendations.push("Enable encryption for all PHI data at rest and in transit".to_string());
                    risk_level = "critical".to_string();
                }
                // Check for audit logging
                let audit = config.get_item("audit")
                    .ok().flatten()
                    .and_then(|v| v.extract::<bool>().ok())
                    .unwrap_or(false);
                if !audit {
                    violations.push("PHI access without audit logging".to_string());
                    recommendations.push("Enable audit logging for all PHI access events".to_string());
                    risk_level = "high".to_string();
                }
            }
        },
        ComplianceStandard::PciDss => {
            // Check for cardholder data handling
            if config_str.contains("card") || config_str.contains("payment") || config_str.contains("credit") {
                let tokenized = config.get_item("tokenized")
                    .ok().flatten()
                    .and_then(|v| v.extract::<bool>().ok())
                    .unwrap_or(false);
                if !tokenized {
                    violations.push("Cardholder data without tokenization".to_string());
                    recommendations.push("Implement tokenization for all cardholder data".to_string());
                    risk_level = "critical".to_string();
                }
            }
        },
        ComplianceStandard::Gdpr => {
            // Check for PII handling
            if config_str.contains("personal") || config_str.contains("pii") || config_str.contains("user_data") {
                let consent = config.get_item("consent_verified")
                    .ok().flatten()
                    .and_then(|v| v.extract::<bool>().ok())
                    .unwrap_or(false);
                if !consent {
                    violations.push("PII processing without consent verification".to_string());
                    recommendations.push("Verify user consent before processing personal data".to_string());
                    risk_level = "high".to_string();
                }
                let retention = config.get_item("retention_policy")
                    .ok().flatten()
                    .and_then(|v| v.extract::<String>().ok())
                    .unwrap_or_default();
                if retention.is_empty() {
                    violations.push("No retention policy specified for personal data".to_string());
                    recommendations.push("Define data retention and deletion policy".to_string());
                    if risk_level != "critical" { risk_level = "medium".to_string(); }
                }
            }
        },
        ComplianceStandard::Sox => {
            // Check for financial record integrity
            if config_str.contains("financial") || config_str.contains("audit") || config_str.contains("report") {
                let immutable = config.get_item("immutable")
                    .ok().flatten()
                    .and_then(|v| v.extract::<bool>().ok())
                    .unwrap_or(false);
                if !immutable {
                    violations.push("Financial records without immutability guarantee".to_string());
                    recommendations.push("Enable append-only audit trail for financial records".to_string());
                    risk_level = "high".to_string();
                }
            }
        },
        ComplianceStandard::AmlKyc => {
            // Check for transaction monitoring
            if config_str.contains("transfer") || config_str.contains("transaction") {
                let kyc_verified = config.get_item("kyc_verified")
                    .ok().flatten()
                    .and_then(|v| v.extract::<bool>().ok())
                    .unwrap_or(false);
                if !kyc_verified {
                    violations.push("Transaction without KYC verification".to_string());
                    recommendations.push("Complete KYC verification before processing transactions".to_string());
                    risk_level = "critical".to_string();
                }
            }
        },
        ComplianceStandard::Coppa => {
            // Check for child data handling
            if config_str.contains("child") || config_str.contains("minor") || config_str.contains("student") {
                let parental_consent = config.get_item("parental_consent")
                    .ok().flatten()
                    .and_then(|v| v.extract::<bool>().ok())
                    .unwrap_or(false);
                if !parental_consent {
                    violations.push("Minor data processing without parental consent".to_string());
                    recommendations.push("Obtain verifiable parental consent before collecting minor data".to_string());
                    risk_level = "critical".to_string();
                }
            }
        },
        _ => {
            // Generic compliance checks for FedRAMP, ISO27001, SOC2, PCI-DSS 1.2
            let access_control = config.get_item("access_control")
                .ok().flatten()
                .and_then(|v| v.extract::<bool>().ok())
                .unwrap_or(false);
            if !access_control && !config_str.is_empty() {
                recommendations.push("Implement role-based access control".to_string());
                if risk_level == "low" { risk_level = "medium".to_string(); }
            }
        },
    }

    let compliant = violations.is_empty();
    ComplianceCheckResult {
        standard: standard.as_str().to_string(),
        compliant,
        violations,
        recommendations,
        risk_level,
    }
}
