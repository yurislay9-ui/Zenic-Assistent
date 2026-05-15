//! Domain-specific safety rules — 5 rules per NicheCategory = 35 total.
//!
//! Each rule is deterministic: regex-based pattern matching.
//! Domain rules can only ESCALATE verdicts, never downgrade.

use regex::Regex;
use serde::{Deserialize, Serialize};
use std::fmt;

use crate::categories::NicheCategory;
use crate::verdict::{ActionCategory, SafetyVerdict};

// ---------------------------------------------------------------------------
// DomainRule
// ---------------------------------------------------------------------------

/// A single domain-specific safety rule.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DomainRule {
    /// Unique rule name (e.g., "fintech_unauthorized_transfer").
    pub name: String,
    /// The niche category this rule applies to.
    pub niche_category: NicheCategory,
    /// Human-readable description.
    pub description: String,
    /// The action category this rule targets.
    pub action_category: ActionCategory,
    /// Regex pattern to detect the condition.
    pub pattern: String,
    /// The verdict to apply when the pattern matches.
    pub verdict: SafetyVerdict,
    /// Human-readable message shown when triggered.
    pub message: String,
    /// Associated compliance standards (if any).
    pub compliance_standards: Vec<String>,

    #[serde(skip)]
    compiled: Option<Regex>,
}

impl DomainRule {
    /// Create a new domain rule.
    pub fn new(
        name: &str,
        niche_category: NicheCategory,
        description: &str,
        action_category: ActionCategory,
        pattern: &str,
        verdict: SafetyVerdict,
        message: &str,
        compliance_standards: Vec<&str>,
    ) -> Self {
        let compiled = Regex::new(pattern).ok();
        Self {
            name: name.to_string(),
            niche_category,
            description: description.to_string(),
            action_category,
            pattern: pattern.to_string(),
            verdict,
            message: message.to_string(),
            compliance_standards: compliance_standards.iter().map(|s| s.to_string()).collect(),
            compiled,
        }
    }

    /// Check if this rule matches the given action config.
    pub fn matches(&self, action_type: &str, config: &serde_json::Value) -> bool {
        if let Some(ref re) = self.compiled {
            let searchable = Self::to_searchable(action_type, config);
            re.is_match(&searchable)
        } else {
            false
        }
    }

    /// Convert action type + config to a searchable string.
    fn to_searchable(action_type: &str, config: &serde_json::Value) -> String {
        let mut parts = vec![action_type.to_string()];
        if let Some(obj) = config.as_object() {
            for (key, value) in obj {
                parts.push(format!("{}={}", key, value));
            }
        } else {
            parts.push(config.to_string());
        }
        parts.join(" ")
    }
}

impl fmt::Display for DomainRule {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "DomainRule({}:{})", self.niche_category, self.name)
    }
}

// ---------------------------------------------------------------------------
// DomainRuleSet
// ---------------------------------------------------------------------------

/// A collection of domain-specific safety rules, organized by category.
pub struct DomainRuleSet {
    rules: Vec<DomainRule>,
}

impl DomainRuleSet {
    /// Create the full set of 35 domain-specific rules.
    pub fn new() -> Self {
        Self {
            rules: Self::build_all_rules(),
        }
    }

    /// Get rules for a specific niche category.
    pub fn rules_for_category(&self, category: NicheCategory) -> Vec<&DomainRule> {
        self.rules.iter().filter(|r| r.niche_category == category).collect()
    }

    /// Check all rules for a category against the given action.
    pub fn check(
        &self,
        category: NicheCategory,
        action_type: &str,
        config: &serde_json::Value,
    ) -> Vec<&DomainRule> {
        self.rules
            .iter()
            .filter(|r| r.niche_category == category && r.matches(action_type, config))
            .collect()
    }

    /// Get all rules.
    pub fn all_rules(&self) -> &[DomainRule] {
        &self.rules
    }

    /// Total rule count.
    pub fn len(&self) -> usize {
        self.rules.len()
    }

    /// Whether the set is empty.
    pub fn is_empty(&self) -> bool {
        self.rules.is_empty()
    }

    // ── Rule Definitions ──────────────────────────────────────

    /// Build all 35 domain-specific safety rules.
    fn build_all_rules() -> Vec<DomainRule> {
        let mut rules = Vec::with_capacity(35);
        rules.extend(Self::ai_data_rules());
        rules.extend(Self::fintech_rules());
        rules.extend(Self::healthtech_rules());
        rules.extend(Self::greentech_rules());
        rules.extend(Self::edtech_rules());
        rules.extend(Self::proptech_rules());
        rules.extend(Self::legaltech_rules());
        rules
    }

    /// Reglas de IA y Datos (5).
    fn ai_data_rules() -> Vec<DomainRule> {
        vec![
            DomainRule::new(
                "ai_data_model_retrain",
                NicheCategory::AiData,
                "ML model retraining without validation gate",
                ActionCategory::System,
                r"(?:retrain|re-train|model_update|model_refresh)",
                SafetyVerdict::Approve,
                "ML model retraining requires approval — unvalidated models can produce harmful predictions",
                vec!["iso_27001", "soc2"],
            ),
            DomainRule::new(
                "ai_data_bulk_export",
                NicheCategory::AiData,
                "Bulk data export from analytics pipeline",
                ActionCategory::Destructive,
                r"(?:bulk_export|mass_export|download_all|export_dataset)",
                SafetyVerdict::Confirm,
                "Bulk data export requires confirmation — verify data classification before export",
                vec!["gdpr"],
            ),
            DomainRule::new(
                "ai_data_pii_access",
                NicheCategory::AiData,
                "Access to PII training data",
                ActionCategory::Moderate,
                r"(?:pii|personal_data|sensitive_data|personally_identifiable)",
                SafetyVerdict::Approve,
                "PII data access requires approval — GDPR/privacy compliance required",
                vec!["gdpr", "soc2"],
            ),
            DomainRule::new(
                "ai_data_pipeline_config",
                NicheCategory::AiData,
                "Data pipeline configuration change",
                ActionCategory::System,
                r"(?:pipeline_config|etl_change|data_flow_modify)",
                SafetyVerdict::Confirm,
                "Pipeline configuration change requires confirmation — data integrity at risk",
                vec!["iso_27001"],
            ),
            DomainRule::new(
                "ai_data_prediction_override",
                NicheCategory::AiData,
                "Manual override of AI predictions",
                ActionCategory::Moderate,
                r"(?:prediction_override|manual_override|force_prediction|override_ai)",
                SafetyVerdict::Confirm,
                "Manual AI prediction override requires confirmation — audit trail required",
                vec!["soc2"],
            ),
        ]
    }

    /// Reglas de Tecnología Financiera (5).
    fn fintech_rules() -> Vec<DomainRule> {
        vec![
            DomainRule::new(
                "fintech_unauthorized_transfer",
                NicheCategory::FinTech,
                "Unauthorized financial transfer attempt",
                ActionCategory::Financial,
                r"(?:transfer|send_money|wire|remittance).*(?:unauthorized|unverified|without_approval)",
                SafetyVerdict::Deny,
                "Unauthorized financial transfer — DENIED per AML/KYC compliance",
                vec!["aml_kyc", "pci_dss"],
            ),
            DomainRule::new(
                "fintech_large_transaction",
                NicheCategory::FinTech,
                "Large financial transaction without dual approval",
                ActionCategory::Financial,
                r"(?:large_transaction|big_transfer|high_value).*(?:amount|value|sum)",
                SafetyVerdict::Approve,
                "Large transaction requires dual approval — SOX compliance",
                vec!["sox", "aml_kyc"],
            ),
            DomainRule::new(
                "fintech_rate_change",
                NicheCategory::FinTech,
                "Interest rate or fee modification",
                ActionCategory::Financial,
                r"(?:interest_rate|fee_change|rate_modify|apr_change|commission_update)",
                SafetyVerdict::Approve,
                "Rate modification requires approval — regulatory compliance required",
                vec!["sox", "pci_dss"],
            ),
            DomainRule::new(
                "fintech_account_closure",
                NicheCategory::FinTech,
                "Customer account closure",
                ActionCategory::Destructive,
                r"(?:account_close|close_account|terminate_account|account_closure)",
                SafetyVerdict::Confirm,
                "Account closure requires confirmation — verify pending transactions",
                vec!["aml_kyc"],
            ),
            DomainRule::new(
                "fintech_compliance_bypass",
                NicheCategory::FinTech,
                "Attempt to bypass compliance checks",
                ActionCategory::Destructive,
                r"(?:bypass_compliance|skip_kyc|override_aml|ignore_check)",
                SafetyVerdict::Deny,
                "Compliance bypass attempt — ABSOLUTELY DENIED — regulatory violation",
                vec!["aml_kyc", "sox", "pci_dss"],
            ),
        ]
    }

    /// Reglas de Tecnología de la Salud (5).
    fn healthtech_rules() -> Vec<DomainRule> {
        vec![
            DomainRule::new(
                "healthtech_phi_access",
                NicheCategory::HealthTech,
                "Access to Protected Health Information",
                ActionCategory::Moderate,
                r"(?:phi|health_record|medical_record|patient_data|clinical_data)",
                SafetyVerdict::Approve,
                "PHI access requires approval — HIPAA compliance required",
                vec!["hipaa"],
            ),
            DomainRule::new(
                "healthtech_prescription_mod",
                NicheCategory::HealthTech,
                "Prescription modification without authorization",
                ActionCategory::Destructive,
                r"(?:prescription|medication).*(?:modify|change|update|alter)",
                SafetyVerdict::Deny,
                "Unauthorized prescription modification — DENIED per patient safety",
                vec!["hipaa"],
            ),
            DomainRule::new(
                "healthtech_diagnosis_override",
                NicheCategory::HealthTech,
                "Manual diagnosis override in clinical system",
                ActionCategory::Moderate,
                r"(?:diagnosis_override|override_diagnosis|clinical_override|force_diagnosis)",
                SafetyVerdict::Approve,
                "Diagnosis override requires medical professional approval",
                vec!["hipaa", "soc2"],
            ),
            DomainRule::new(
                "healthtech_patient_export",
                NicheCategory::HealthTech,
                "Patient data export",
                ActionCategory::Destructive,
                r"(?:patient_export|export_patient|download_records|medical_data_export)",
                SafetyVerdict::Confirm,
                "Patient data export requires confirmation — verify HIPAA compliance",
                vec!["hipaa", "gdpr"],
            ),
            DomainRule::new(
                "healthtech_device_config",
                NicheCategory::HealthTech,
                "Medical device configuration change",
                ActionCategory::System,
                r"(?:device_config|wearable_config|monitor_setup|device_calibration)",
                SafetyVerdict::Confirm,
                "Medical device configuration change requires confirmation",
                vec!["hipaa"],
            ),
        ]
    }

    /// Reglas de Tecnología Verde (5).
    fn greentech_rules() -> Vec<DomainRule> {
        vec![
            DomainRule::new(
                "greentech_carbon_adjust",
                NicheCategory::GreenTech,
                "Carbon credit adjustment",
                ActionCategory::Financial,
                r"(?:carbon_credit|credit_adjust|offset_modify|emission_offset)",
                SafetyVerdict::Approve,
                "Carbon credit adjustment requires approval — audit trail required",
                vec!["iso_27001"],
            ),
            DomainRule::new(
                "greentech_grid_reconfig",
                NicheCategory::GreenTech,
                "Smart grid reconfiguration",
                ActionCategory::System,
                r"(?:grid_reconfig|smart_grid_change|load_balance_modify|grid_topology)",
                SafetyVerdict::Confirm,
                "Grid reconfiguration requires confirmation — infrastructure stability at risk",
                vec!["iso_27001"],
            ),
            DomainRule::new(
                "greentech_sensor_override",
                NicheCategory::GreenTech,
                "Environmental sensor override",
                ActionCategory::Moderate,
                r"(?:sensor_override|override_sensor|bypass_monitor|ignore_reading)",
                SafetyVerdict::Confirm,
                "Sensor override requires confirmation — data integrity at risk",
                vec!["iso_27001"],
            ),
            DomainRule::new(
                "greentech_waste_reclassify",
                NicheCategory::GreenTech,
                "Waste classification change",
                ActionCategory::Moderate,
                r"(?:waste_reclassify|reclassify_waste|waste_category_change|hazardous_reclass)",
                SafetyVerdict::Approve,
                "Waste reclassification requires approval — regulatory compliance",
                vec!["iso_27001", "gdpr"],
            ),
            DomainRule::new(
                "greentech_fleet_decommission",
                NicheCategory::GreenTech,
                "EV fleet decommission",
                ActionCategory::Destructive,
                r"(?:fleet_decommission|decommission_ev|retire_vehicle|fleet_remove)",
                SafetyVerdict::Confirm,
                "Fleet decommission requires confirmation — verify asset tracking",
                vec!["iso_27001"],
            ),
        ]
    }

    /// Reglas de Tecnología Educativa (5).
    fn edtech_rules() -> Vec<DomainRule> {
        vec![
            DomainRule::new(
                "edtech_minor_data",
                NicheCategory::EdTech,
                "Access to minor/student data",
                ActionCategory::Moderate,
                r"(?:minor_data|student_data|child_data|underage|under_18)",
                SafetyVerdict::Approve,
                "Minor data access requires approval — COPPA compliance required",
                vec!["coppa"],
            ),
            DomainRule::new(
                "edtech_grade_modify",
                NicheCategory::EdTech,
                "Grade or assessment modification",
                ActionCategory::Destructive,
                r"(?:grade_modify|change_grade|assessment_override|score_change)",
                SafetyVerdict::Deny,
                "Unauthorized grade modification — DENIED per academic integrity",
                vec!["coppa", "soc2"],
            ),
            DomainRule::new(
                "edtech_content_filter",
                NicheCategory::EdTech,
                "Content filter bypass attempt",
                ActionCategory::System,
                r"(?:filter_bypass|bypass_filter|content_unblock|unblock_site)",
                SafetyVerdict::Deny,
                "Content filter bypass — DENIED — student safety protection",
                vec!["coppa"],
            ),
            DomainRule::new(
                "edtech_bulk_export",
                NicheCategory::EdTech,
                "Bulk student data export",
                ActionCategory::Destructive,
                r"(?:bulk_student_export|export_roster|download_grades|class_export)",
                SafetyVerdict::Confirm,
                "Bulk student data export requires confirmation — verify COPPA/GDPR compliance",
                vec!["coppa", "gdpr"],
            ),
            DomainRule::new(
                "edtech_curriculum_change",
                NicheCategory::EdTech,
                "Curriculum or course structure change",
                ActionCategory::System,
                r"(?:curriculum_change|course_modify|syllabus_update|learning_path_change)",
                SafetyVerdict::Confirm,
                "Curriculum change requires confirmation — impact on enrolled students",
                vec!["soc2"],
            ),
        ]
    }

    /// Reglas de Tecnología Inmobiliaria (5).
    fn proptech_rules() -> Vec<DomainRule> {
        vec![
            DomainRule::new(
                "proptech_transaction",
                NicheCategory::PropTech,
                "Property transaction without verification",
                ActionCategory::Financial,
                r"(?:property_transaction|real_estate_deal|buy_property|sell_property)",
                SafetyVerdict::Approve,
                "Property transaction requires approval — verify legal compliance",
                vec!["sox", "gdpr"],
            ),
            DomainRule::new(
                "proptech_lease_terminate",
                NicheCategory::PropTech,
                "Lease early termination",
                ActionCategory::Destructive,
                r"(?:lease_terminate|terminate_lease|cancel_lease|early_termination)",
                SafetyVerdict::Confirm,
                "Lease termination requires confirmation — verify contractual obligations",
                vec!["sox"],
            ),
            DomainRule::new(
                "proptech_valuation_change",
                NicheCategory::PropTech,
                "Property valuation modification",
                ActionCategory::Financial,
                r"(?:valuation_change|appraisal_modify|value_adjust|price_revalue)",
                SafetyVerdict::Approve,
                "Valuation change requires approval — SOX compliance for financial reporting",
                vec!["sox", "iso_27001"],
            ),
            DomainRule::new(
                "proptech_tenant_data",
                NicheCategory::PropTech,
                "Tenant personal data access",
                ActionCategory::Moderate,
                r"(?:tenant_data|tenant_info|renter_data|occupant_info)",
                SafetyVerdict::Confirm,
                "Tenant data access requires confirmation — GDPR privacy compliance",
                vec!["gdpr"],
            ),
            DomainRule::new(
                "proptech_access_control",
                NicheCategory::PropTech,
                "Building access control modification",
                ActionCategory::System,
                r"(?:access_control|door_config|security_system|building_access)",
                SafetyVerdict::Confirm,
                "Access control modification requires confirmation — physical security",
                vec!["iso_27001"],
            ),
        ]
    }

    /// Reglas de Tecnología Jurídica (5).
    fn legaltech_rules() -> Vec<DomainRule> {
        vec![
            DomainRule::new(
                "legaltech_contract_exec",
                NicheCategory::LegalTech,
                "Contract execution without review",
                ActionCategory::Financial,
                r"(?:contract_execute|execute_contract|sign_contract|contract_sign)",
                SafetyVerdict::Approve,
                "Contract execution requires approval — legal review mandatory",
                vec!["sox", "soc2"],
            ),
            DomainRule::new(
                "legaltech_document_delete",
                NicheCategory::LegalTech,
                "Legal document deletion",
                ActionCategory::Destructive,
                r"(?:document_delete|delete_legal|destroy_record|purge_document)",
                SafetyVerdict::Deny,
                "Legal document deletion — DENIED — document retention policy",
                vec!["sox", "soc2"],
            ),
            DomainRule::new(
                "legaltech_privilege",
                NicheCategory::LegalTech,
                "Attorney-client privilege data access",
                ActionCategory::Moderate,
                r"(?:privilege|attorney_client|legal_privilege|work_product)",
                SafetyVerdict::Approve,
                "Privileged data access requires approval — attorney-client privilege protection",
                vec!["soc2", "iso_27001"],
            ),
            DomainRule::new(
                "legaltech_compliance_config",
                NicheCategory::LegalTech,
                "Compliance monitoring configuration change",
                ActionCategory::System,
                r"(?:compliance_config|monitor_change|alert_threshold|compliance_rule_modify)",
                SafetyVerdict::Confirm,
                "Compliance config change requires confirmation — regulatory coverage at risk",
                vec!["sox", "iso_27001"],
            ),
            DomainRule::new(
                "legaltech_ip_transfer",
                NicheCategory::LegalTech,
                "Intellectual property transfer",
                ActionCategory::Financial,
                r"(?:ip_transfer|patent_transfer|trademark_assign|copyright_transfer)",
                SafetyVerdict::Approve,
                "IP transfer requires approval — legal verification mandatory",
                vec!["sox", "soc2", "gdpr"],
            ),
        ]
    }
}

impl Default for DomainRuleSet {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn domain_rule_set_has_35_rules() {
        let ruleset = DomainRuleSet::new();
        assert_eq!(ruleset.len(), 35);
    }

    #[test]
    fn five_rules_per_category() {
        let ruleset = DomainRuleSet::new();
        for cat in NicheCategory::ALL {
            let rules = ruleset.rules_for_category(cat);
            assert_eq!(rules.len(), 5, "Expected 5 rules for {:?}", cat);
        }
    }

    #[test]
    fn fintech_compliance_bypass_denied() {
        let ruleset = DomainRuleSet::new();
        let config = serde_json::json!({"action": "bypass_compliance", "target": "kyc_check"});
        let matches = ruleset.check(NicheCategory::FinTech, "compliance_operation", &config);
        assert!(matches.iter().any(|r| r.name == "fintech_compliance_bypass"));
        let rule = matches.iter().find(|r| r.name == "fintech_compliance_bypass").unwrap();
        assert_eq!(rule.verdict, SafetyVerdict::Deny);
    }

    #[test]
    fn healthtech_phi_requires_approval() {
        let ruleset = DomainRuleSet::new();
        let config = serde_json::json!({"action": "phi_access", "data_type": "health_record"});
        let matches = ruleset.check(NicheCategory::HealthTech, "data_access", &config);
        assert!(matches.iter().any(|r| r.name == "healthtech_phi_access"));
        let rule = matches.iter().find(|r| r.name == "healthtech_phi_access").unwrap();
        assert_eq!(rule.verdict, SafetyVerdict::Approve);
    }

    #[test]
    fn edtech_grade_modify_denied() {
        let ruleset = DomainRuleSet::new();
        let config = serde_json::json!({"action": "grade_modify", "target": "student_score"});
        let matches = ruleset.check(NicheCategory::EdTech, "academic_operation", &config);
        assert!(matches.iter().any(|r| r.name == "edtech_grade_modify"));
    }

    #[test]
    fn no_match_returns_empty() {
        let ruleset = DomainRuleSet::new();
        let config = serde_json::json!({"action": "view_dashboard"});
        let matches = ruleset.check(NicheCategory::AiData, "read_operation", &config);
        assert!(matches.is_empty());
    }

    #[test]
    fn domain_rule_display() {
        let ruleset = DomainRuleSet::new();
        let rules = ruleset.rules_for_category(NicheCategory::FinTech);
        assert!(rules[0].to_string().contains("fintech"));
    }
}
