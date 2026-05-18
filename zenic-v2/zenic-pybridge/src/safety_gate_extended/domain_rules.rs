//! Compiled domain safety rules and category-compliance mapping.
//!
//! Contains the 35 compiled domain rules (5 per NicheCategory) and the
//! `CATEGORY_COMPLIANCE` map that associates each niche with its required
//! compliance standards. Both are `pub(crate)` — internal to this crate.

use once_cell::sync::Lazy;
use regex::Regex;
use std::collections::HashMap;

use crate::niche::NicheCategory;
use crate::safety_gate::SafetyVerdict;
use super::types::ComplianceStandard;

// ═══════════════════════════════════════════════════════════════
//  Compiled Domain Safety Rules (35 rules: 5 per NicheCategory)
// ═══════════════════════════════════════════════════════════════

pub(crate) struct CompiledDomainRule {
    pub(crate) name: &'static str,
    pub(crate) category: NicheCategory,
    pub(crate) pattern: Regex,
    pub(crate) verdict: SafetyVerdict,
    pub(crate) message: &'static str,
    pub(crate) compliance: Vec<ComplianceStandard>,
}

pub(crate) static DOMAIN_RULES: Lazy<Vec<CompiledDomainRule>> = Lazy::new(|| {
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
pub(crate) static CATEGORY_COMPLIANCE: Lazy<HashMap<NicheCategory, Vec<ComplianceStandard>>> = Lazy::new(|| {
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
