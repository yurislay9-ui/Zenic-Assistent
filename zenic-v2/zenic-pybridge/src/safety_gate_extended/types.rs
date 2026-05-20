//! PyO3-exposed types for the extended safety gate.
//!
//! - `ComplianceStandard` — regulatory compliance standard enum
//! - `DomainSafetyRule` — a safety rule scoped to a NicheCategory
//! - `ComplianceCheckResult` — result of a compliance validation
//! - `DomainSafetyCheckResult` — extended safety check result with domain info

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════
//  ComplianceStandard — regulatory compliance standards
// ═══════════════════════════════════════════════════════════════

/// Regulatory compliance standard for niche blueprints.
///
/// Each standard maps to specific validation rules that must be
/// satisfied before a blueprint action can proceed.
#[pyclass(name = "ComplianceStandard", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum ComplianceStandard {
    Hipaa,
    PciDss,
    Gdpr,
    Sox,
    AmlKyc,
    FedRamp,
    Iso27001,
    Soc2,
    Coppa,
    PciDss12,
}

impl ComplianceStandard {
    /// Return the Python-enum string value.
    pub fn as_str(&self) -> &'static str {
        match self {
            ComplianceStandard::Hipaa => "hipaa",
            ComplianceStandard::PciDss => "pci_dss",
            ComplianceStandard::Gdpr => "gdpr",
            ComplianceStandard::Sox => "sox",
            ComplianceStandard::AmlKyc => "aml_kyc",
            ComplianceStandard::FedRamp => "fedramp",
            ComplianceStandard::Iso27001 => "iso_27001",
            ComplianceStandard::Soc2 => "soc2",
            ComplianceStandard::Coppa => "coppa",
            ComplianceStandard::PciDss12 => "pci_dss_12",
        }
    }

    /// Human-readable display name.
    pub fn display_name(&self) -> &'static str {
        match self {
            ComplianceStandard::Hipaa => "HIPAA",
            ComplianceStandard::PciDss => "PCI-DSS",
            ComplianceStandard::Gdpr => "GDPR",
            ComplianceStandard::Sox => "SOX",
            ComplianceStandard::AmlKyc => "AML/KYC",
            ComplianceStandard::FedRamp => "FedRAMP",
            ComplianceStandard::Iso27001 => "ISO 27001",
            ComplianceStandard::Soc2 => "SOC 2",
            ComplianceStandard::Coppa => "COPPA",
            ComplianceStandard::PciDss12 => "PCI-DSS 1.2",
        }
    }

    /// All variants.
    pub fn all() -> &'static [ComplianceStandard] {
        &[
            ComplianceStandard::Hipaa,
            ComplianceStandard::PciDss,
            ComplianceStandard::Gdpr,
            ComplianceStandard::Sox,
            ComplianceStandard::AmlKyc,
            ComplianceStandard::FedRamp,
            ComplianceStandard::Iso27001,
            ComplianceStandard::Soc2,
            ComplianceStandard::Coppa,
            ComplianceStandard::PciDss12,
        ]
    }
}

#[pymethods]
impl ComplianceStandard {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("ComplianceStandard.{}", self.display_name().replace(' ', "").replace('/', "").replace('-', ""))
    }
}

// ═══════════════════════════════════════════════════════════════
//  DomainSafetyRule — safety rule scoped to a NicheCategory
// ═══════════════════════════════════════════════════════════════

/// A safety rule scoped to a specific niche category.
///
/// Domain rules are evaluated AFTER the base 10 rules. They can
/// only ESCALATE verdicts (e.g., ALLOW → CONFIRM, CONFIRM → APPROVE,
/// APPROVE → DENY). They cannot downgrade verdicts.
#[pyclass(name = "DomainSafetyRule")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DomainSafetyRule {
    pub(crate) name: String,
    pub(crate) niche_category: String,
    pub(crate) pattern_str: String,
    pub(crate) verdict_str: String,
    pub(crate) message: String,
    pub(crate) compliance_standards: Vec<String>,
}

impl DomainSafetyRule {
    /// Create a new DomainSafetyRule.
    pub fn new(
        name: String,
        niche_category: String,
        pattern_str: String,
        verdict_str: String,
        message: String,
        compliance_standards: Vec<String>,
    ) -> Self {
        DomainSafetyRule {
            name,
            niche_category,
            pattern_str,
            verdict_str,
            message,
            compliance_standards,
        }
    }
}

#[pymethods]
impl DomainSafetyRule {
    #[getter]
    fn name(&self) -> &str {
        &self.name
    }

    #[getter]
    fn niche_category(&self) -> &str {
        &self.niche_category
    }

    #[getter]
    fn pattern(&self) -> &str {
        &self.pattern_str
    }

    #[getter]
    fn verdict(&self) -> &str {
        &self.verdict_str
    }

    #[getter]
    fn message(&self) -> &str {
        &self.message
    }

    #[getter]
    fn compliance_standards(&self) -> Vec<String> {
        self.compliance_standards.clone()
    }

    fn __repr__(&self) -> String {
        format!(
            "DomainSafetyRule(name={:?}, category={:?}, verdict={:?})",
            self.name, self.niche_category, self.verdict_str,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  ComplianceCheckResult — result of compliance validation
// ═══════════════════════════════════════════════════════════════

/// Result of checking an action against a compliance standard.
#[pyclass(name = "ComplianceCheckResult")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ComplianceCheckResult {
    pub(crate) standard: String,
    pub(crate) compliant: bool,
    pub(crate) violations: Vec<String>,
    pub(crate) recommendations: Vec<String>,
    pub(crate) risk_level: String,
}

#[pymethods]
impl ComplianceCheckResult {
    #[getter]
    fn standard(&self) -> &str {
        &self.standard
    }

    #[getter]
    fn compliant(&self) -> bool {
        self.compliant
    }

    #[getter]
    fn violations(&self) -> Vec<String> {
        self.violations.clone()
    }

    #[getter]
    fn recommendations(&self) -> Vec<String> {
        self.recommendations.clone()
    }

    #[getter]
    fn risk_level(&self) -> &str {
        &self.risk_level
    }

    fn __repr__(&self) -> String {
        format!(
            "ComplianceCheckResult(standard={:?}, compliant={}, violations={})",
            self.standard,
            self.compliant,
            self.violations.len(),
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  DomainSafetyCheckResult — extended safety check result
// ═══════════════════════════════════════════════════════════════

/// Extended safety check result including domain and compliance info.
#[pyclass(name = "DomainSafetyCheckResult")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DomainSafetyCheckResult {
    pub(crate) base_verdict: String,
    pub(crate) domain_verdict: String,
    pub(crate) final_verdict: String,
    pub(crate) niche_category: String,
    pub(crate) data_sensitivity: String,
    pub(crate) domain_rules_matched: Vec<String>,
    pub(crate) compliance_results: Vec<ComplianceCheckResult>,
    pub(crate) escalation_applied: bool,
    pub(crate) reason: String,
    pub(crate) can_proceed: bool,
}

#[pymethods]
impl DomainSafetyCheckResult {
    #[getter]
    fn base_verdict(&self) -> &str {
        &self.base_verdict
    }

    #[getter]
    fn domain_verdict(&self) -> &str {
        &self.domain_verdict
    }

    #[getter]
    fn final_verdict(&self) -> &str {
        &self.final_verdict
    }

    #[getter]
    fn niche_category(&self) -> &str {
        &self.niche_category
    }

    #[getter]
    fn data_sensitivity(&self) -> &str {
        &self.data_sensitivity
    }

    #[getter]
    fn domain_rules_matched(&self) -> Vec<String> {
        self.domain_rules_matched.clone()
    }

    #[getter]
    fn compliance_results(&self) -> Vec<ComplianceCheckResult> {
        self.compliance_results.clone()
    }

    #[getter]
    fn escalation_applied(&self) -> bool {
        self.escalation_applied
    }

    #[getter]
    fn reason(&self) -> &str {
        &self.reason
    }

    #[getter]
    fn can_proceed(&self) -> bool {
        self.can_proceed
    }

    fn __repr__(&self) -> String {
        format!(
            "DomainSafetyCheckResult(final={}, category={:?}, escalation={}, can_proceed={})",
            self.final_verdict, self.niche_category, self.escalation_applied, self.can_proceed,
        )
    }
}
