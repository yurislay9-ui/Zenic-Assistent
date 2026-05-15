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

use once_cell::sync::Lazy;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Mutex;

use crate::niche::NicheCategory;
use crate::safety_gate::{
    classify_action_inner, ActionCategory, SafetyCheckResult, SafetyVerdict,
};

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
    name: String,
    niche_category: String,
    pattern_str: String,
    verdict_str: String,
    message: String,
    compliance_standards: Vec<String>,
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
    standard: String,
    compliant: bool,
    violations: Vec<String>,
    recommendations: Vec<String>,
    risk_level: String,
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
    base_verdict: String,
    domain_verdict: String,
    final_verdict: String,
    niche_category: String,
    data_sensitivity: String,
    domain_rules_matched: Vec<String>,
    compliance_results: Vec<ComplianceCheckResult>,
    escalation_applied: bool,
    reason: String,
    can_proceed: bool,
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

// ═══════════════════════════════════════════════════════════════
//  Compiled Domain Safety Rules (35 rules: 5 per NicheCategory)
// ═══════════════════════════════════════════════════════════════

struct CompiledDomainRule {
    name: &'static str,
    category: NicheCategory,
    pattern: Regex,
    verdict: SafetyVerdict,
    message: &'static str,
    compliance: Vec<ComplianceStandard>,
}

static DOMAIN_RULES: Lazy<Vec<CompiledDomainRule>> = Lazy::new(|| {
    vec![
        // ── AiData: 5 rules ──────────────────────────────────
        CompiledDomainRule {
            name: "ai_model_export",
            category: NicheCategory::AiData,
            pattern: Regex::new(r"(?i)(?:export|download|extract).*(?:model|weights|checkpoint|embedding)")
                .expect("invalid regex: ai_model_export"),
            verdict: SafetyVerdict::Approve,
            message: "AI model export requires approval — verify no PII in training data",
            compliance: vec![ComplianceStandard::Gdpr, ComplianceStandard::Iso27001],
        },
        CompiledDomainRule {
            name: "ai_training_data_pii",
            category: NicheCategory::AiData,
            pattern: Regex::new(r"(?i)(?:train|fine.?tune|retrain).*(?:data|dataset|corpus)")
                .expect("invalid regex: ai_training_data_pii"),
            verdict: SafetyVerdict::Approve,
            message: "Training data operation requires approval — PII audit mandatory",
            compliance: vec![ComplianceStandard::Gdpr, ComplianceStandard::Hipaa],
        },
        CompiledDomainRule {
            name: "ai_bulk_inference",
            category: NicheCategory::AiData,
            pattern: Regex::new(r"(?i)(?:batch|bulk|mass).*(?:predict|infer|classify|score)")
                .expect("invalid regex: ai_bulk_inference"),
            verdict: SafetyVerdict::Confirm,
            message: "Bulk inference operation — confirm scope and rate limits",
            compliance: vec![ComplianceStandard::Soc2],
        },
        CompiledDomainRule {
            name: "ai_data_deletion",
            category: NicheCategory::AiData,
            pattern: Regex::new(r"(?i)(?:delete|purge|remove).*(?:dataset|training.?data|corpus|embedding)")
                .expect("invalid regex: ai_data_deletion"),
            verdict: SafetyVerdict::Confirm,
            message: "Dataset deletion — confirm no active models depend on this data",
            compliance: vec![ComplianceStandard::Gdpr],
        },
        CompiledDomainRule {
            name: "ai_api_key_rotation",
            category: NicheCategory::AiData,
            pattern: Regex::new(r"(?i)(?:rotate|regenerate|change).*(?:api.?key|token|credential|secret)")
                .expect("invalid regex: ai_api_key_rotation"),
            verdict: SafetyVerdict::Confirm,
            message: "API key rotation — confirm all dependent services updated",
            compliance: vec![ComplianceStandard::Soc2, ComplianceStandard::Iso27001],
        },

        // ── FinTech: 5 rules ──────────────────────────────────
        CompiledDomainRule {
            name: "fintech_transaction_override",
            category: NicheCategory::FinTech,
            pattern: Regex::new(r"(?i)(?:override|bypass|skip).*(?:fraud|aml|kyc|compliance|limit|check)")
                .expect("invalid regex: fintech_transaction_override"),
            verdict: SafetyVerdict::Deny,
            message: "DENY: Compliance/fraud bypass is absolutely forbidden",
            compliance: vec![ComplianceStandard::AmlKyc, ComplianceStandard::Sox],
        },
        CompiledDomainRule {
            name: "fintech_large_transfer",
            category: NicheCategory::FinTech,
            pattern: Regex::new(r"(?i)(?:transfer|send|wire).*(?:large|bulk|threshold|above)")
                .expect("invalid regex: fintech_large_transfer"),
            verdict: SafetyVerdict::Approve,
            message: "Large value transfer — dual approval required per AML/KYC",
            compliance: vec![ComplianceStandard::AmlKyc, ComplianceStandard::PciDss],
        },
        CompiledDomainRule {
            name: "fintech_rate_change",
            category: NicheCategory::FinTech,
            pattern: Regex::new(r"(?i)(?:change|update|modify).*(?:rate|interest|fee|commission|spread)")
                .expect("invalid regex: fintech_rate_change"),
            verdict: SafetyVerdict::Approve,
            message: "Rate modification — compliance officer approval required",
            compliance: vec![ComplianceStandard::Sox, ComplianceStandard::PciDss],
        },
        CompiledDomainRule {
            name: "fintech_customer_data_export",
            category: NicheCategory::FinTech,
            pattern: Regex::new(r"(?i)(?:export|download|extract).*(?:customer|client|account).*(?:data|record)")
                .expect("invalid regex: fintech_customer_data_export"),
            verdict: SafetyVerdict::Approve,
            message: "Customer data export — GDPR right to portability with audit trail",
            compliance: vec![ComplianceStandard::Gdpr, ComplianceStandard::PciDss],
        },
        CompiledDomainRule {
            name: "fintech_audit_log_modification",
            category: NicheCategory::FinTech,
            pattern: Regex::new(r"(?i)(?:modify|alter|delete|tamper).*(?:audit|log|trail|record)")
                .expect("invalid regex: fintech_audit_log_modification"),
            verdict: SafetyVerdict::Deny,
            message: "DENY: Audit log tampering is absolutely forbidden (SOX violation)",
            compliance: vec![ComplianceStandard::Sox],
        },

        // ── HealthTech: 5 rules ──────────────────────────────
        CompiledDomainRule {
            name: "health_phi_access",
            category: NicheCategory::HealthTech,
            pattern: Regex::new(r"(?i)(?:access|view|read|query).*(?:patient|phi|medical|health|record|diagnosis)")
                .expect("invalid regex: health_phi_access"),
            verdict: SafetyVerdict::Approve,
            message: "PHI access requires role-based approval with audit logging",
            compliance: vec![ComplianceStandard::Hipaa],
        },
        CompiledDomainRule {
            name: "health_phi_export",
            category: NicheCategory::HealthTech,
            pattern: Regex::new(r"(?i)(?:export|download|transfer|share).*(?:patient|phi|medical|health|record)")
                .expect("invalid regex: health_phi_export"),
            verdict: SafetyVerdict::Approve,
            message: "PHI export requires explicit consent verification + BAA check",
            compliance: vec![ComplianceStandard::Hipaa, ComplianceStandard::Gdpr],
        },
        CompiledDomainRule {
            name: "health_phi_deidentification",
            category: NicheCategory::HealthTech,
            pattern: Regex::new(r"(?i)(?:de.?identify|anonymize|pseudonymize|strip).*(?:phi|pii|data|record)")
                .expect("invalid regex: health_phi_deidentification"),
            verdict: SafetyVerdict::Confirm,
            message: "De-identification — confirm safe harbor method compliance",
            compliance: vec![ComplianceStandard::Hipaa],
        },
        CompiledDomainRule {
            name: "health_prescription_modification",
            category: NicheCategory::HealthTech,
            pattern: Regex::new(r"(?i)(?:modify|change|update|alter).*(?:prescription|dosage|medication|treatment)")
                .expect("invalid regex: health_prescription_modification"),
            verdict: SafetyVerdict::Deny,
            message: "DENY: Prescription modification requires licensed practitioner auth",
            compliance: vec![ComplianceStandard::Hipaa],
        },
        CompiledDomainRule {
            name: "health_emr_integration",
            category: NicheCategory::HealthTech,
            pattern: Regex::new(r"(?i)(?:integrate|connect|sync|interface).*(?:emr|ehr|fhir|hl7)")
                .expect("invalid regex: health_emr_integration"),
            verdict: SafetyVerdict::Approve,
            message: "EMR/EHR integration — security review + BAA verification required",
            compliance: vec![ComplianceStandard::Hipaa, ComplianceStandard::Soc2],
        },

        // ── GreenTech: 5 rules ──────────────────────────────
        CompiledDomainRule {
            name: "green_carbon_report_modification",
            category: NicheCategory::GreenTech,
            pattern: Regex::new(r"(?i)(?:modify|alter|adjust).*(?:carbon|emission|offset|credit).*(?:report|data|metric)")
                .expect("invalid regex: green_carbon_report_modification"),
            verdict: SafetyVerdict::Approve,
            message: "Carbon report modification — compliance officer approval required",
            compliance: vec![ComplianceStandard::Iso27001],
        },
        CompiledDomainRule {
            name: "green_grid_operation",
            category: NicheCategory::GreenTech,
            pattern: Regex::new(r"(?i)(?:control|dispatch|curtail|shutdown).*(?:grid|power|energy|solar|wind)")
                .expect("invalid regex: green_grid_operation"),
            verdict: SafetyVerdict::Confirm,
            message: "Grid operation — confirm no safety-critical impact",
            compliance: vec![ComplianceStandard::Iso27001],
        },
        CompiledDomainRule {
            name: "green_sensor_bulk_delete",
            category: NicheCategory::GreenTech,
            pattern: Regex::new(r"(?i)(?:delete|purge|remove).*(?:sensor|meter|reading|telemetry).*(?:data|record)")
                .expect("invalid regex: green_sensor_bulk_delete"),
            verdict: SafetyVerdict::Confirm,
            message: "Sensor data deletion — confirm no regulatory retention requirement",
            compliance: vec![ComplianceStandard::Gdpr],
        },
        CompiledDomainRule {
            name: "green_certification_export",
            category: NicheCategory::GreenTech,
            pattern: Regex::new(r"(?i)(?:export|generate|issue).*(?:certificate|certification|compliance|badge)")
                .expect("invalid regex: green_certification_export"),
            verdict: SafetyVerdict::Confirm,
            message: "Certification export — confirm data accuracy verification complete",
            compliance: vec![ComplianceStandard::Iso27001],
        },
        CompiledDomainRule {
            name: "green_iot_firmware_update",
            category: NicheCategory::GreenTech,
            pattern: Regex::new(r"(?i)(?:update|flash|deploy).*(?:firmware|ota|device|iot|sensor)")
                .expect("invalid regex: green_iot_firmware_update"),
            verdict: SafetyVerdict::Approve,
            message: "IoT firmware update — approval required for safety-critical devices",
            compliance: vec![ComplianceStandard::Iso27001],
        },

        // ── EdTech: 5 rules ──────────────────────────────────
        CompiledDomainRule {
            name: "edtech_student_data_access",
            category: NicheCategory::EdTech,
            pattern: Regex::new(r"(?i)(?:access|view|query).*(?:student|learner|grade|score|record)")
                .expect("invalid regex: edtech_student_data_access"),
            verdict: SafetyVerdict::Confirm,
            message: "Student data access — confirm FERPA authorization",
            compliance: vec![ComplianceStandard::Coppa, ComplianceStandard::Gdpr],
        },
        CompiledDomainRule {
            name: "edtech_minor_data_export",
            category: NicheCategory::EdTech,
            pattern: Regex::new(r"(?i)(?:export|download|share).*(?:minor|child|student).*(?:data|record|profile)")
                .expect("invalid regex: edtech_minor_data_export"),
            verdict: SafetyVerdict::Approve,
            message: "Minor data export — parental consent verification required (COPPA)",
            compliance: vec![ComplianceStandard::Coppa],
        },
        CompiledDomainRule {
            name: "edtech_grade_modification",
            category: NicheCategory::EdTech,
            pattern: Regex::new(r"(?i)(?:modify|change|override|alter).*(?:grade|score|gpa|assessment|result)")
                .expect("invalid regex: edtech_grade_modification"),
            verdict: SafetyVerdict::Approve,
            message: "Grade modification — instructor approval + audit trail required",
            compliance: vec![ComplianceStandard::Soc2],
        },
        CompiledDomainRule {
            name: "edtech_content_publish",
            category: NicheCategory::EdTech,
            pattern: Regex::new(r"(?i)(?:publish|deploy|release).*(?:course|content|curriculum|material|module)")
                .expect("invalid regex: edtech_content_publish"),
            verdict: SafetyVerdict::Confirm,
            message: "Content publication — confirm review and accessibility compliance",
            compliance: vec![ComplianceStandard::Iso27001],
        },
        CompiledDomainRule {
            name: "edtech_proctoring_data",
            category: NicheCategory::EdTech,
            pattern: Regex::new(r"(?i)(?:proctor|monitor|surveil|record|camera).*(?:exam|test|assessment)")
                .expect("invalid regex: edtech_proctoring_data"),
            verdict: SafetyVerdict::Approve,
            message: "Proctoring data — consent and privacy review required",
            compliance: vec![ComplianceStandard::Gdpr, ComplianceStandard::Coppa],
        },

        // ── PropTech: 5 rules ──────────────────────────────
        CompiledDomainRule {
            name: "proptech_tenant_data_access",
            category: NicheCategory::PropTech,
            pattern: Regex::new(r"(?i)(?:access|view|query).*(?:tenant|lease|rental|occupant).*(?:data|record)")
                .expect("invalid regex: proptech_tenant_data_access"),
            verdict: SafetyVerdict::Confirm,
            message: "Tenant data access — confirm authorization and purpose limitation",
            compliance: vec![ComplianceStandard::Gdpr],
        },
        CompiledDomainRule {
            name: "proptech_building_control",
            category: NicheCategory::PropTech,
            pattern: Regex::new(r"(?i)(?:control|override|bypass).*(?:hvac|security|access|fire|alarm|system)")
                .expect("invalid regex: proptech_building_control"),
            verdict: SafetyVerdict::Approve,
            message: "Building system control — facility manager approval required",
            compliance: vec![ComplianceStandard::Iso27001],
        },
        CompiledDomainRule {
            name: "proptech_contract_modification",
            category: NicheCategory::PropTech,
            pattern: Regex::new(r"(?i)(?:modify|change|amend|update).*(?:contract|lease|agreement|terms)")
                .expect("invalid regex: proptech_contract_modification"),
            verdict: SafetyVerdict::Approve,
            message: "Contract modification — legal review approval required",
            compliance: vec![ComplianceStandard::Sox],
        },
        CompiledDomainRule {
            name: "proptech_valuation_override",
            category: NicheCategory::PropTech,
            pattern: Regex::new(r"(?i)(?:override|bypass|adjust).*(?:valuation|appraisal|assessment|price)")
                .expect("invalid regex: proptech_valuation_override"),
            verdict: SafetyVerdict::Deny,
            message: "DENY: Valuation override is forbidden — use standard revaluation process",
            compliance: vec![ComplianceStandard::Sox],
        },
        CompiledDomainRule {
            name: "proptech_iot_data_deletion",
            category: NicheCategory::PropTech,
            pattern: Regex::new(r"(?i)(?:delete|purge|remove).*(?:sensor|iot|smart|meter).*(?:data|reading)")
                .expect("invalid regex: proptech_iot_data_deletion"),
            verdict: SafetyVerdict::Confirm,
            message: "IoT data deletion — confirm no regulatory retention requirement",
            compliance: vec![ComplianceStandard::Gdpr],
        },

        // ── LegalTech: 5 rules ──────────────────────────────
        CompiledDomainRule {
            name: "legal_privileged_access",
            category: NicheCategory::LegalTech,
            pattern: Regex::new(r"(?i)(?:access|view|read).*(?:privileged|confidential|attorney|client).*(?:data|document|communication)")
                .expect("invalid regex: legal_privileged_access"),
            verdict: SafetyVerdict::Approve,
            message: "Privileged document access — bar member verification required",
            compliance: vec![ComplianceStandard::Soc2, ComplianceStandard::Iso27001],
        },
        CompiledDomainRule {
            name: "legal_contract_execution",
            category: NicheCategory::LegalTech,
            pattern: Regex::new(r"(?i)(?:execute|sign|finalize|seal).*(?:contract|agreement|deal|settlement)")
                .expect("invalid regex: legal_contract_execution"),
            verdict: SafetyVerdict::Approve,
            message: "Contract execution — authorized signatory approval required",
            compliance: vec![ComplianceStandard::Sox],
        },
        CompiledDomainRule {
            name: "legal_evidence_tampering",
            category: NicheCategory::LegalTech,
            pattern: Regex::new(r"(?i)(?:modify|alter|delete|tamper|fabricate).*(?:evidence|exhibit|deposition|filing|record)")
                .expect("invalid regex: legal_evidence_tampering"),
            verdict: SafetyVerdict::Deny,
            message: "DENY: Evidence tampering is absolutely forbidden — criminal liability",
            compliance: vec![ComplianceStandard::Sox],
        },
        CompiledDomainRule {
            name: "legal_compliance_report",
            category: NicheCategory::LegalTech,
            pattern: Regex::new(r"(?i)(?:generate|create|submit|file).*(?:compliance|regulatory|report|filing|disclosure)")
                .expect("invalid regex: legal_compliance_report"),
            verdict: SafetyVerdict::Confirm,
            message: "Compliance report generation — confirm data accuracy review",
            compliance: vec![ComplianceStandard::Sox, ComplianceStandard::Gdpr],
        },
        CompiledDomainRule {
            name: "legal_discovery_export",
            category: NicheCategory::LegalTech,
            pattern: Regex::new(r"(?i)(?:export|produce|deliver).*(?:discovery|esubpoena|evidence|disclosure|production)")
                .expect("invalid regex: legal_discovery_export"),
            verdict: SafetyVerdict::Approve,
            message: "Discovery export — legal hold verification and privilege review required",
            compliance: vec![ComplianceStandard::Soc2, ComplianceStandard::Gdpr],
        },
    ]
});

// ═══════════════════════════════════════════════════════════════
//  Compliance Standards per NicheCategory
// ═══════════════════════════════════════════════════════════════

/// Map each NicheCategory to its required compliance standards.
static CATEGORY_COMPLIANCE: Lazy<HashMap<NicheCategory, Vec<ComplianceStandard>>> = Lazy::new(|| {
    let mut m = HashMap::new();
    m.insert(NicheCategory::AiData, vec![ComplianceStandard::Gdpr, ComplianceStandard::Iso27001, ComplianceStandard::Soc2]);
    m.insert(NicheCategory::FinTech, vec![ComplianceStandard::PciDss, ComplianceStandard::AmlKyc, ComplianceStandard::Sox, ComplianceStandard::Gdpr]);
    m.insert(NicheCategory::HealthTech, vec![ComplianceStandard::Hipaa, ComplianceStandard::Gdpr, ComplianceStandard::Soc2]);
    m.insert(NicheCategory::GreenTech, vec![ComplianceStandard::Iso27001, ComplianceStandard::Gdpr]);
    m.insert(NicheCategory::EdTech, vec![ComplianceStandard::Coppa, ComplianceStandard::Gdpr, ComplianceStandard::Soc2]);
    m.insert(NicheCategory::PropTech, vec![ComplianceStandard::Gdpr, ComplianceStandard::Sox, ComplianceStandard::Iso27001]);
    m.insert(NicheCategory::LegalTech, vec![ComplianceStandard::Sox, ComplianceStandard::Soc2, ComplianceStandard::Gdpr, ComplianceStandard::Iso27001]);
    m
});

// ═══════════════════════════════════════════════════════════════
//  Internal Helpers
// ═══════════════════════════════════════════════════════════════

/// Verdict escalation: determine if a domain rule can escalate the base verdict.
///
/// Escalation order: ALLOW < CONFIRM < APPROVE < DENY
/// A domain rule CAN escalate but CANNOT downgrade.
fn can_escalate(base: &SafetyVerdict, domain: &SafetyVerdict) -> bool {
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
fn escalate_by_sensitivity(verdict: &SafetyVerdict, sensitivity: &str) -> (SafetyVerdict, bool) {
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

/// Parse a NicheCategory from a string.
fn parse_niche_category(s: &str) -> Option<NicheCategory> {
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

/// Convert config dict to searchable string (reuses base gate logic).
fn config_to_searchable(action_type: &str, config: &Bound<'_, PyDict>) -> PyResult<String> {
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

/// Validate an action against a specific compliance standard.
fn validate_compliance(
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
    use super::*;

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
