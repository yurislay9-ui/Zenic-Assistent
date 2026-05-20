//! PyO3-exposed functions for the extended safety gate.
//!
//! Public API functions that are registered in `lib.rs`:
//!
//! - `safety_validate_extended` — full 4-layer validation pipeline
//! - `safety_validate_domain` — domain-specific rule matching
//! - `safety_check_compliance` — single compliance check
//! - `safety_check_compliance_batch` — batch compliance check
//! - `safety_get_domain_rules` — list rules for a domain
//! - `safety_escalate_verdict` — sensitivity escalation
//! - `safety_get_compliance_for_category` — compliance standards for domain

use pyo3::prelude::*;
use pyo3::types::PyDict;

use crate::safety_gate::SafetyVerdict;
use super::types::{ComplianceCheckResult, ComplianceStandard, DomainSafetyCheckResult, DomainSafetyRule};
use super::domain_rules::{CATEGORY_COMPLIANCE, DOMAIN_RULES};
use super::helpers::{
    can_escalate, config_to_searchable, escalate_by_sensitivity, parse_niche_category,
    validate_compliance,
};

// ═══════════════════════════════════════════════════════════════
//  PyO3 Functions — Public API
// ═══════════════════════════════════════════════════════════════

/// Full extended safety validation pipeline.
///
/// Runs the complete 4-layer validation:
/// 1. Base SafetyGate (10 generic rules)
/// 2. Domain-specific rules (5 per NicheCategory)
/// 3. Compliance checks per standard
/// 4. Sensitivity escalation
///
/// Parameters
/// ----------
/// action_type : str
///     The type of action being performed.
/// config : dict
///     Configuration dict with action-specific parameters.
/// category_str : str
///     NicheCategory string (e.g., "fintech", "healthtech").
/// sensitivity_str : str
///     DataSensitivity string (e.g., "low", "medium", "high", "critical").
///
/// Returns
/// -------
/// DomainSafetyCheckResult
///     Extended safety check result with domain and compliance info.
#[pyfunction]
#[pyo3(signature = (action_type, config, category_str, sensitivity_str))]
pub fn safety_validate_extended(
    action_type: &str,
    config: &Bound<'_, PyDict>,
    category_str: &str,
    sensitivity_str: &str,
    py: Python<'_>,
) -> PyResult<DomainSafetyCheckResult> {
    // Step 1: Base SafetyGate validation
    let base_result = crate::safety_gate::safety_validate(action_type, config)?;
    let base_verdict_str = base_result.verdict().as_str().to_string();
    let mut current_verdict = base_result.verdict().clone();
    let mut domain_rules_matched: Vec<String> = Vec::new();

    // Step 2: Domain-specific rules
    if let Some(niche_category) = parse_niche_category(category_str) {
        let searchable = config_to_searchable(action_type, config)?;

        for rule in DOMAIN_RULES.iter() {
            if rule.category != niche_category {
                continue;
            }
            if rule.pattern.is_match(&searchable) {
                domain_rules_matched.push(rule.name.to_string());
                // Domain rules can only ESCALATE
                if can_escalate(&current_verdict, &rule.verdict) {
                    current_verdict = rule.verdict.clone();
                }
                // DENY from domain rules is absolute
                if rule.verdict == SafetyVerdict::Deny {
                    current_verdict = SafetyVerdict::Deny;
                    break;
                }
            }
        }
    }

    let domain_verdict_str = current_verdict.as_str().to_string();

    // Step 3: Compliance checks
    let mut compliance_results: Vec<ComplianceCheckResult> = Vec::new();
    if let Some(niche_category) = parse_niche_category(category_str) {
        if let Some(standards) = CATEGORY_COMPLIANCE.get(&niche_category) {
            for standard in standards {
                let result = validate_compliance(config, *standard, py);
                // Compliance failures for critical violations → DENY
                if result.risk_level == "critical" && !result.compliant {
                    current_verdict = SafetyVerdict::Deny;
                }
                compliance_results.push(result);
            }
        }
    }

    // Step 4: Sensitivity escalation
    let (final_verdict, escalation_applied) = escalate_by_sensitivity(&current_verdict, sensitivity_str);

    let can_proceed = !matches!(final_verdict, SafetyVerdict::Deny | SafetyVerdict::RateLimited);

    let reason = if final_verdict == SafetyVerdict::Deny {
        "Action denied: base rule, domain rule, compliance failure, or sensitivity escalation".to_string()
    } else if escalation_applied {
        format!("Verdict escalated from {} to {} due to {} sensitivity", domain_verdict_str, final_verdict.as_str(), sensitivity_str)
    } else if !domain_rules_matched.is_empty() {
        format!("Domain rule(s) matched: {}", domain_rules_matched.join(", "))
    } else {
        base_result.reason().to_string()
    };

    Ok(DomainSafetyCheckResult {
        base_verdict: base_verdict_str,
        domain_verdict: domain_verdict_str,
        final_verdict: final_verdict.as_str().to_string(),
        niche_category: category_str.to_string(),
        data_sensitivity: sensitivity_str.to_string(),
        domain_rules_matched,
        compliance_results,
        escalation_applied,
        reason,
        can_proceed,
    })
}

/// Validate an action against domain-specific rules only.
///
/// Parameters
/// ----------
/// action_type : str
///     The type of action being performed.
/// config : dict
///     Configuration dict.
/// niche_category : str
///     NicheCategory string (e.g., "fintech").
///
/// Returns
/// -------
/// list[str]
///     Names of matching domain rules.
#[pyfunction]
pub fn safety_validate_domain(
    action_type: &str,
    config: &Bound<'_, PyDict>,
    niche_category: &str,
) -> PyResult<Vec<String>> {
    let category = match parse_niche_category(niche_category) {
        Some(c) => c,
        None => return Ok(Vec::new()),
    };

    let searchable = config_to_searchable(action_type, config)?;
    let mut matched: Vec<String> = Vec::new();

    for rule in DOMAIN_RULES.iter() {
        if rule.category != category {
            continue;
        }
        if rule.pattern.is_match(&searchable) {
            matched.push(rule.name.to_string());
        }
    }

    Ok(matched)
}

/// Check an action against a specific compliance standard.
///
/// Parameters
/// ----------
/// config : dict
///     Configuration dict.
/// standard : ComplianceStandard
///     The compliance standard to check against.
///
/// Returns
/// -------
/// ComplianceCheckResult
///     Result of the compliance check.
#[pyfunction]
pub fn safety_check_compliance(
    config: &Bound<'_, PyDict>,
    standard: ComplianceStandard,
    py: Python<'_>,
) -> ComplianceCheckResult {
    validate_compliance(config, standard, py)
}

/// Check an action against multiple compliance standards.
///
/// Parameters
/// ----------
/// config : dict
///     Configuration dict.
/// standards : list[ComplianceStandard]
///     List of compliance standards to check.
///
/// Returns
/// -------
/// list[ComplianceCheckResult]
///     Results for each standard.
#[pyfunction]
pub fn safety_check_compliance_batch(
    config: &Bound<'_, PyDict>,
    standards: Vec<ComplianceStandard>,
    py: Python<'_>,
) -> Vec<ComplianceCheckResult> {
    standards.iter().map(|s| validate_compliance(config, *s, py)).collect()
}

/// Get all domain safety rules for a niche category.
///
/// Parameters
/// ----------
/// niche_category : str
///     NicheCategory string.
///
/// Returns
/// -------
/// list[DomainSafetyRule]
///     Domain rules for the specified category.
#[pyfunction]
pub fn safety_get_domain_rules(niche_category: &str) -> Vec<DomainSafetyRule> {
    let category = match parse_niche_category(niche_category) {
        Some(c) => c,
        None => return Vec::new(),
    };

    DOMAIN_RULES
        .iter()
        .filter(|r| r.category == category)
        .map(|r| DomainSafetyRule {
            name: r.name.to_string(),
            niche_category: r.category.as_str().to_string(),
            pattern_str: r.pattern.as_str().to_string(),
            verdict_str: r.verdict.as_str().to_string(),
            message: r.message.to_string(),
            compliance_standards: r.compliance.iter().map(|c| c.as_str().to_string()).collect(),
        })
        .collect()
}

/// Escalate a verdict based on data sensitivity level.
///
/// Parameters
/// ----------
/// base_verdict_str : str
///     The base verdict string ("ALLOW", "CONFIRM", "APPROVE", "DENY").
/// sensitivity_str : str
///     Data sensitivity level ("low", "medium", "high", "critical").
///
/// Returns
/// -------
/// tuple[str, bool]
///     (escalated_verdict_str, was_escalated).
#[pyfunction]
pub fn safety_escalate_verdict(
    base_verdict_str: &str,
    sensitivity_str: &str,
) -> (String, bool) {
    let base = match base_verdict_str.to_uppercase().as_str() {
        "ALLOW" => SafetyVerdict::Allow,
        "CONFIRM" => SafetyVerdict::Confirm,
        "APPROVE" => SafetyVerdict::Approve,
        "DENY" => SafetyVerdict::Deny,
        "RATE_LIMITED" => SafetyVerdict::RateLimited,
        _ => SafetyVerdict::Confirm,
    };
    let (escalated, was_escalated) = escalate_by_sensitivity(&base, sensitivity_str);
    (escalated.as_str().to_string(), was_escalated)
}

/// Get the compliance standards required for a niche category.
///
/// Parameters
/// ----------
/// niche_category : str
///     NicheCategory string.
///
/// Returns
/// -------
/// list[str]
///     Compliance standard strings for the category.
#[pyfunction]
pub fn safety_get_compliance_for_category(niche_category: &str) -> Vec<String> {
    let category = match parse_niche_category(niche_category) {
        Some(c) => c,
        None => return Vec::new(),
    };

    CATEGORY_COMPLIANCE
        .get(&category)
        .map(|standards| standards.iter().map(|s| s.as_str().to_string()).collect())
        .unwrap_or_default()
}

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use crate::niche::NicheCategory;
    use crate::safety_gate::SafetyVerdict;
    use super::super::domain_rules::{DOMAIN_RULES, CATEGORY_COMPLIANCE};
    use super::super::helpers::{can_escalate, escalate_by_sensitivity, parse_niche_category};
    use super::super::types::ComplianceStandard;

    #[test]
    fn test_compliance_standard_str_roundtrip() {
        assert_eq!(ComplianceStandard::Hipaa.as_str(), "hipaa");
        assert_eq!(ComplianceStandard::PciDss.as_str(), "pci_dss");
        assert_eq!(ComplianceStandard::Gdpr.as_str(), "gdpr");
        assert_eq!(ComplianceStandard::Sox.as_str(), "sox");
        assert_eq!(ComplianceStandard::AmlKyc.as_str(), "aml_kyc");
    }

    #[test]
    fn test_compliance_standard_display_names() {
        assert_eq!(ComplianceStandard::Hipaa.display_name(), "HIPAA");
        assert_eq!(ComplianceStandard::PciDss.display_name(), "PCI-DSS");
        assert_eq!(ComplianceStandard::AmlKyc.display_name(), "AML/KYC");
    }

    #[test]
    fn test_all_35_domain_rules_compiled() {
        assert_eq!(DOMAIN_RULES.len(), 35);
    }

    #[test]
    fn test_domain_rules_distribution() {
        for category in NicheCategory::all() {
            let count = DOMAIN_RULES.iter().filter(|r| r.category == *category).count();
            assert_eq!(count, 5, "Category {:?} should have 5 rules, got {}", category, count);
        }
    }

    #[test]
    fn test_can_escalate_allow_to_confirm() {
        assert!(can_escalate(&SafetyVerdict::Allow, &SafetyVerdict::Confirm));
        assert!(can_escalate(&SafetyVerdict::Allow, &SafetyVerdict::Approve));
        assert!(can_escalate(&SafetyVerdict::Allow, &SafetyVerdict::Deny));
    }

    #[test]
    fn test_cannot_escalate_downward() {
        assert!(!can_escalate(&SafetyVerdict::Deny, &SafetyVerdict::Allow));
        assert!(!can_escalate(&SafetyVerdict::Approve, &SafetyVerdict::Confirm));
        assert!(!can_escalate(&SafetyVerdict::Confirm, &SafetyVerdict::Allow));
    }

    #[test]
    fn test_escalate_by_sensitivity_critical() {
        let (v, escalated) = escalate_by_sensitivity(&SafetyVerdict::Allow, "critical");
        assert_eq!(v, SafetyVerdict::Confirm);
        assert!(escalated);

        let (v, escalated) = escalate_by_sensitivity(&SafetyVerdict::Confirm, "critical");
        assert_eq!(v, SafetyVerdict::Approve);
        assert!(escalated);

        let (v, escalated) = escalate_by_sensitivity(&SafetyVerdict::Approve, "critical");
        assert_eq!(v, SafetyVerdict::Deny);
        assert!(escalated);
    }

    #[test]
    fn test_escalate_by_sensitivity_high() {
        let (v, escalated) = escalate_by_sensitivity(&SafetyVerdict::Allow, "high");
        assert_eq!(v, SafetyVerdict::Confirm);
        assert!(escalated);

        let (v, escalated) = escalate_by_sensitivity(&SafetyVerdict::Confirm, "high");
        assert_eq!(v, SafetyVerdict::Approve);
        assert!(escalated);
    }

    #[test]
    fn test_escalate_by_sensitivity_low_no_change() {
        let (v, escalated) = escalate_by_sensitivity(&SafetyVerdict::Allow, "low");
        assert_eq!(v, SafetyVerdict::Allow);
        assert!(!escalated);

        let (v, escalated) = escalate_by_sensitivity(&SafetyVerdict::Confirm, "medium");
        assert_eq!(v, SafetyVerdict::Confirm);
        assert!(!escalated);
    }

    #[test]
    fn test_parse_niche_category() {
        assert_eq!(parse_niche_category("fintech"), Some(NicheCategory::FinTech));
        assert_eq!(parse_niche_category("healthtech"), Some(NicheCategory::HealthTech));
        assert_eq!(parse_niche_category("unknown"), None);
        assert_eq!(parse_niche_category(""), None);
    }

    #[test]
    fn test_category_compliance_mapping() {
        let fintech = CATEGORY_COMPLIANCE.get(&NicheCategory::FinTech).unwrap();
        assert!(fintech.contains(&ComplianceStandard::PciDss));
        assert!(fintech.contains(&ComplianceStandard::AmlKyc));

        let health = CATEGORY_COMPLIANCE.get(&NicheCategory::HealthTech).unwrap();
        assert!(health.contains(&ComplianceStandard::Hipaa));
    }

    #[test]
    fn test_fintech_deny_rules() {
        // Test that compliance bypass is denied
        let override_rule = DOMAIN_RULES.iter().find(|r| r.name == "fintech_transaction_override").unwrap();
        assert_eq!(override_rule.verdict, SafetyVerdict::Deny);

        // Test audit log tampering is denied
        let audit_rule = DOMAIN_RULES.iter().find(|r| r.name == "fintech_audit_log_modification").unwrap();
        assert_eq!(audit_rule.verdict, SafetyVerdict::Deny);
    }

    #[test]
    fn test_healthtech_deny_rules() {
        let prescription = DOMAIN_RULES.iter().find(|r| r.name == "health_prescription_modification").unwrap();
        assert_eq!(prescription.verdict, SafetyVerdict::Deny);
    }

    #[test]
    fn test_legaltech_deny_rules() {
        let evidence = DOMAIN_RULES.iter().find(|r| r.name == "legal_evidence_tampering").unwrap();
        assert_eq!(evidence.verdict, SafetyVerdict::Deny);
    }

    #[test]
    fn test_proptech_deny_rules() {
        let valuation = DOMAIN_RULES.iter().find(|r| r.name == "proptech_valuation_override").unwrap();
        assert_eq!(valuation.verdict, SafetyVerdict::Deny);
    }
}
