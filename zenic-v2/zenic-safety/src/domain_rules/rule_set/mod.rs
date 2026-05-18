//! DomainRuleSet: collection of domain-specific safety rules, organized by category.

mod rules_health_green;
mod rules_edu_prop_legal;

use crate::categories::NicheCategory;
use crate::verdict::{ActionCategory, SafetyVerdict};

use super::rule_types::DomainRule;

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
}

impl Default for DomainRuleSet {
    fn default() -> Self {
        Self::new()
    }
}
