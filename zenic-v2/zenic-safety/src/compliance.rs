//! Compliance validation engine — regulatory standards checker.
//!
//! Supports 8 compliance standards:
//!   HIPAA, PCI-DSS, GDPR, SOX, AML/KYC, COPPA, ISO 27001, SOC 2
//!
//! Each standard has a set of deterministic validation rules that check
//! the action config against regulatory requirements.

use serde::{Deserialize, Serialize};
use std::fmt;

use crate::categories::NicheCategory;

// ---------------------------------------------------------------------------
// ComplianceStandard
// ---------------------------------------------------------------------------

/// Regulatory compliance standards supported by the safety gate.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ComplianceStandard {
    /// Health Insurance Portability and Accountability Act (US)
    Hipaa,
    /// Payment Card Industry Data Security Standard
    PciDss,
    /// General Data Protection Regulation (EU)
    Gdpr,
    /// Sarbanes-Oxley Act (US)
    Sox,
    /// Anti-Money Laundering / Know Your Customer
    AmlKyc,
    /// Children's Online Privacy Protection Act (US)
    Coppa,
    /// ISO/IEC 27001 Information Security Management
    Iso27001,
    /// SOC 2 Type II Service Organization Control
    Soc2,
}

impl ComplianceStandard {
    /// All standards.
    pub const ALL: [ComplianceStandard; 8] = [
        ComplianceStandard::Hipaa,
        ComplianceStandard::PciDss,
        ComplianceStandard::Gdpr,
        ComplianceStandard::Sox,
        ComplianceStandard::AmlKyc,
        ComplianceStandard::Coppa,
        ComplianceStandard::Iso27001,
        ComplianceStandard::Soc2,
    ];

    /// String identifier.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Hipaa => "hipaa",
            Self::PciDss => "pci_dss",
            Self::Gdpr => "gdpr",
            Self::Sox => "sox",
            Self::AmlKyc => "aml_kyc",
            Self::Coppa => "coppa",
            Self::Iso27001 => "iso_27001",
            Self::Soc2 => "soc2",
        }
    }

    /// Human-readable name.
    pub fn display_name(&self) -> &'static str {
        match self {
            Self::Hipaa => "HIPAA",
            Self::PciDss => "PCI-DSS",
            Self::Gdpr => "GDPR",
            Self::Sox => "SOX",
            Self::AmlKyc => "AML/KYC",
            Self::Coppa => "COPPA",
            Self::Iso27001 => "ISO 27001",
            Self::Soc2 => "SOC 2",
        }
    }

    /// Parse from string.
    pub fn from_str_lossy(s: &str) -> Option<Self> {
        match s.to_lowercase().replace("-", "_").replace(" ", "").as_str() {
            "hipaa" => Some(Self::Hipaa),
            "pci_dss" | "pcidss" | "pci" => Some(Self::PciDss),
            "gdpr" => Some(Self::Gdpr),
            "sox" => Some(Self::Sox),
            "aml_kyc" | "amlkyc" | "aml" | "kyc" => Some(Self::AmlKyc),
            "coppa" => Some(Self::Coppa),
            "iso_27001" | "iso27001" | "iso2701" => Some(Self::Iso27001),
            "soc2" | "soc_2" | "soc" => Some(Self::Soc2),
            _ => None,
        }
    }
}

impl fmt::Display for ComplianceStandard {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

// ---------------------------------------------------------------------------
// ComplianceResult
// ---------------------------------------------------------------------------

/// Result of a compliance check against a regulatory standard.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComplianceResult {
    /// The standard that was checked.
    pub standard: ComplianceStandard,
    /// Whether the action is compliant with this standard.
    pub compliant: bool,
    /// List of violations found.
    pub violations: Vec<String>,
    /// List of recommendations to achieve compliance.
    pub recommendations: Vec<String>,
    /// Risk level: "low", "medium", "high", "critical".
    pub risk_level: String,
}

impl ComplianceResult {
    /// Create a compliant result with no violations.
    pub fn compliant(standard: ComplianceStandard) -> Self {
        Self {
            standard,
            compliant: true,
            violations: Vec::new(),
            recommendations: Vec::new(),
            risk_level: "low".to_string(),
        }
    }

    /// Create a non-compliant result.
    pub fn non_compliant(
        standard: ComplianceStandard,
        violations: Vec<String>,
        recommendations: Vec<String>,
        risk_level: &str,
    ) -> Self {
        Self {
            standard,
            compliant: false,
            violations,
            recommendations,
            risk_level: risk_level.to_string(),
        }
    }
}

impl fmt::Display for ComplianceResult {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "ComplianceResult({}: {})",
            self.standard.display_name(),
            if self.compliant { "COMPLIANT" } else { "VIOLATION" }
        )
    }
}

// ---------------------------------------------------------------------------
// ComplianceEngine
// ---------------------------------------------------------------------------

/// Engine for checking regulatory compliance of actions.
///
/// Each standard has a set of deterministic rules that check whether
/// the action config satisfies regulatory requirements.
pub struct ComplianceEngine {
    // No mutable state — fully deterministic
}

impl ComplianceEngine {
    /// Create a new compliance engine.
    pub fn new() -> Self {
        Self {}
    }

    /// Check compliance against all standards for a niche category.
    pub fn check_category(
        &self,
        category: NicheCategory,
        action_type: &str,
        config: &serde_json::Value,
    ) -> Vec<ComplianceResult> {
        category
            .compliance_standards()
            .iter()
            .map(|std| self.check_standard(*std, action_type, config))
            .collect()
    }

    /// Check compliance against a specific standard.
    pub fn check_standard(
        &self,
        standard: ComplianceStandard,
        action_type: &str,
        config: &serde_json::Value,
    ) -> ComplianceResult {
        match standard {
            ComplianceStandard::Hipaa => self.check_hipaa(action_type, config),
            ComplianceStandard::PciDss => self.check_pci_dss(action_type, config),
            ComplianceStandard::Gdpr => self.check_gdpr(action_type, config),
            ComplianceStandard::Sox => self.check_sox(action_type, config),
            ComplianceStandard::AmlKyc => self.check_aml_kyc(action_type, config),
            ComplianceStandard::Coppa => self.check_coppa(action_type, config),
            ComplianceStandard::Iso27001 => self.check_iso_27001(action_type, config),
            ComplianceStandard::Soc2 => self.check_soc2(action_type, config),
        }
    }

    /// Check compliance against specific standards given by name.
    pub fn check_standards(
        &self,
        standards: &[ComplianceStandard],
        action_type: &str,
        config: &serde_json::Value,
    ) -> Vec<ComplianceResult> {
        standards
            .iter()
            .map(|std| self.check_standard(*std, action_type, config))
            .collect()
    }

    // ── HIPAA ──────────────────────────────────────────────────

    fn check_hipaa(&self, action_type: &str, config: &serde_json::Value) -> ComplianceResult {
        let mut violations = Vec::new();
        let mut recommendations = Vec::new();
        let mut risk_level = "low".to_string();

        let config_str = config.to_string().to_lowercase();
        let action_lower = action_type.to_lowercase();

        // Rule: PHI access without encryption flag
        if config_str.contains("phi") || config_str.contains("health_record") || config_str.contains("patient_data") {
            if !config_str.contains("encryption") && !config_str.contains("encrypted") {
                violations.push("PHI access without encryption — HIPAA Security Rule violation".to_string());
                recommendations.push("Enable encryption for all PHI data access".to_string());
                risk_level = "critical".to_string();
            }

            if !config_str.contains("audit") && !config_str.contains("logged") {
                violations.push("PHI access without audit trail — HIPAA Audit Control requirement".to_string());
                recommendations.push("Enable audit logging for all PHI access events".to_string());
                if risk_level != "critical" {
                    risk_level = "high".to_string();
                }
            }
        }

        // Rule: Data export without de-identification
        if action_lower.contains("export") || action_lower.contains("download") {
            if config_str.contains("phi") && !config_str.contains("deidentify") && !config_str.contains("de-identify") && !config_str.contains("anonymiz") {
                violations.push("PHI export without de-identification — HIPAA Privacy Rule".to_string());
                recommendations.push("Apply de-identification before exporting PHI data".to_string());
                if risk_level != "critical" {
                    risk_level = "high".to_string();
                }
            }
        }

        if violations.is_empty() {
            ComplianceResult::compliant(ComplianceStandard::Hipaa)
        } else {
            ComplianceResult::non_compliant(ComplianceStandard::Hipaa, violations, recommendations, &risk_level)
        }
    }

    // ── PCI-DSS ────────────────────────────────────────────────

    fn check_pci_dss(&self, _action_type: &str, config: &serde_json::Value) -> ComplianceResult {
        let mut violations = Vec::new();
        let mut recommendations = Vec::new();
        let mut risk_level = "low".to_string();

        let config_str = config.to_string().to_lowercase();

        // Rule: Card data handling without tokenization
        if config_str.contains("card") || config_str.contains("credit") || config_str.contains("pan") {
            if !config_str.contains("tokeniz") && !config_str.contains("token") {
                violations.push("Card data processing without tokenization — PCI-DSS Requirement 3".to_string());
                recommendations.push("Use tokenization for all card data storage and processing".to_string());
                risk_level = "critical".to_string();
            }
        }

        // Rule: Payment processing without logging
        if config_str.contains("payment") || config_str.contains("charge") || config_str.contains("transaction") {
            if !config_str.contains("log") && !config_str.contains("audit") {
                violations.push("Payment processing without audit logging — PCI-DSS Requirement 10".to_string());
                recommendations.push("Enable audit logging for all payment transactions".to_string());
                if risk_level != "critical" {
                    risk_level = "high".to_string();
                }
            }
        }

        if violations.is_empty() {
            ComplianceResult::compliant(ComplianceStandard::PciDss)
        } else {
            ComplianceResult::non_compliant(ComplianceStandard::PciDss, violations, recommendations, &risk_level)
        }
    }

    // ── GDPR ───────────────────────────────────────────────────

    fn check_gdpr(&self, action_type: &str, config: &serde_json::Value) -> ComplianceResult {
        let mut violations = Vec::new();
        let mut recommendations = Vec::new();
        let mut risk_level = "low".to_string();

        let config_str = config.to_string().to_lowercase();
        let action_lower = action_type.to_lowercase();

        // Rule: Personal data processing without consent/legal basis
        if config_str.contains("personal_data") || config_str.contains("pii") || config_str.contains("user_data") {
            if !config_str.contains("consent") && !config_str.contains("legal_basis") && !config_str.contains("legitimate_interest") {
                violations.push("Personal data processing without documented legal basis — GDPR Article 6".to_string());
                recommendations.push("Document legal basis (consent, legitimate interest, etc.) for data processing".to_string());
                risk_level = "high".to_string();
            }
        }

        // Rule: Data deletion request handling
        if action_lower.contains("delete") && (config_str.contains("user") || config_str.contains("personal")) {
            if !config_str.contains("right_to_erasure") && !config_str.contains("gdpr_request") {
                violations.push("User data deletion without GDPR right-to-erasure process — GDPR Article 17".to_string());
                recommendations.push("Implement right-to-erasure process for user data deletion".to_string());
                if risk_level != "critical" {
                    risk_level = "high".to_string();
                }
            }
        }

        // Rule: Cross-border data transfer
        if action_lower.contains("transfer") || action_lower.contains("export") || config_str.contains("transfer") {
            if config_str.contains("international") || config_str.contains("cross_border") || config_str.contains("third_country") {
                if !config_str.contains("scc") && !config_str.contains("adequacy") && !config_str.contains("standard_contractual") {
                    violations.push("International data transfer without safeguards — GDPR Chapter V".to_string());
                    recommendations.push("Ensure adequate safeguards (SCCs, adequacy decision) for international transfers".to_string());
                    risk_level = "critical".to_string();
                }
            }
        }

        if violations.is_empty() {
            ComplianceResult::compliant(ComplianceStandard::Gdpr)
        } else {
            ComplianceResult::non_compliant(ComplianceStandard::Gdpr, violations, recommendations, &risk_level)
        }
    }

    // ── SOX ────────────────────────────────────────────────────

    fn check_sox(&self, _action_type: &str, config: &serde_json::Value) -> ComplianceResult {
        let mut violations = Vec::new();
        let mut recommendations = Vec::new();
        let mut risk_level = "low".to_string();

        let config_str = config.to_string().to_lowercase();

        // Rule: Financial report modification
        if config_str.contains("financial_report") || config_str.contains("accounting") || config_str.contains("ledger") {
            if !config_str.contains("dual_control") && !config_str.contains("segregation") && !config_str.contains("approval") {
                violations.push("Financial data modification without dual control — SOX Section 404".to_string());
                recommendations.push("Implement dual control / segregation of duties for financial modifications".to_string());
                risk_level = "critical".to_string();
            }
        }

        if violations.is_empty() {
            ComplianceResult::compliant(ComplianceStandard::Sox)
        } else {
            ComplianceResult::non_compliant(ComplianceStandard::Sox, violations, recommendations, &risk_level)
        }
    }

    // ── AML/KYC ────────────────────────────────────────────────

    fn check_aml_kyc(&self, _action_type: &str, config: &serde_json::Value) -> ComplianceResult {
        let mut violations = Vec::new();
        let mut recommendations = Vec::new();
        let mut risk_level = "low".to_string();

        let config_str = config.to_string().to_lowercase();

        // Rule: Transaction without KYC verification
        if config_str.contains("transfer") || config_str.contains("transaction") || config_str.contains("payment") {
            if !config_str.contains("kyc_verified") && !config_str.contains("kyc_check") && !config_str.contains("identity_verified") {
                violations.push("Financial transaction without KYC verification — AML compliance risk".to_string());
                recommendations.push("Verify customer identity (KYC) before processing transactions".to_string());
                risk_level = "critical".to_string();
            }
        }

        // Rule: High-value transaction without enhanced due diligence
        if config_str.contains("high_value") || config_str.contains("large_amount") {
            if !config_str.contains("edd") && !config_str.contains("enhanced_due_diligence") {
                violations.push("High-value transaction without Enhanced Due Diligence — FATF Recommendation".to_string());
                recommendations.push("Apply Enhanced Due Diligence for high-value transactions".to_string());
                if risk_level != "critical" {
                    risk_level = "high".to_string();
                }
            }
        }

        if violations.is_empty() {
            ComplianceResult::compliant(ComplianceStandard::AmlKyc)
        } else {
            ComplianceResult::non_compliant(ComplianceStandard::AmlKyc, violations, recommendations, &risk_level)
        }
    }

    // ── COPPA ──────────────────────────────────────────────────

    fn check_coppa(&self, _action_type: &str, config: &serde_json::Value) -> ComplianceResult {
        let mut violations = Vec::new();
        let mut recommendations = Vec::new();
        let mut risk_level = "low".to_string();

        let config_str = config.to_string().to_lowercase();

        // Rule: Collection of children's data without parental consent
        if config_str.contains("minor") || config_str.contains("child") || config_str.contains("under_13") || config_str.contains("student") {
            if !config_str.contains("parental_consent") && !config_str.contains("guardian_approval") {
                violations.push("Children's data collection without parental consent — COPPA Section 3".to_string());
                recommendations.push("Obtain verifiable parental consent before collecting children's data".to_string());
                risk_level = "critical".to_string();
            }
        }

        if violations.is_empty() {
            ComplianceResult::compliant(ComplianceStandard::Coppa)
        } else {
            ComplianceResult::non_compliant(ComplianceStandard::Coppa, violations, recommendations, &risk_level)
        }
    }

    // ── ISO 27001 ──────────────────────────────────────────────

    fn check_iso_27001(&self, _action_type: &str, config: &serde_json::Value) -> ComplianceResult {
        let mut violations = Vec::new();
        let mut recommendations = Vec::new();
        let mut risk_level = "low".to_string();

        let config_str = config.to_string().to_lowercase();

        // Rule: System change without change management
        if config_str.contains("config_change") || config_str.contains("system_modify") || config_str.contains("infrastructure_change") {
            if !config_str.contains("change_management") && !config_str.contains("change_request") && !config_str.contains("approval") {
                violations.push("System change without change management process — ISO 27001 Annex A.12".to_string());
                recommendations.push("Route system changes through formal change management process".to_string());
                risk_level = "high".to_string();
            }
        }

        if violations.is_empty() {
            ComplianceResult::compliant(ComplianceStandard::Iso27001)
        } else {
            ComplianceResult::non_compliant(ComplianceStandard::Iso27001, violations, recommendations, &risk_level)
        }
    }

    // ── SOC 2 ──────────────────────────────────────────────────

    fn check_soc2(&self, _action_type: &str, config: &serde_json::Value) -> ComplianceResult {
        let mut violations = Vec::new();
        let mut recommendations = Vec::new();
        let mut risk_level = "low".to_string();

        let config_str = config.to_string().to_lowercase();

        // Rule: Data access without monitoring
        if config_str.contains("data_access") || config_str.contains("sensitive_data") || config_str.contains("api_key") {
            if !config_str.contains("monitored") && !config_str.contains("audit") && !config_str.contains("logging") {
                violations.push("Sensitive data access without monitoring — SOC 2 CC6.1".to_string());
                recommendations.push("Enable monitoring and audit logging for sensitive data access".to_string());
                risk_level = "high".to_string();
            }
        }

        if violations.is_empty() {
            ComplianceResult::compliant(ComplianceStandard::Soc2)
        } else {
            ComplianceResult::non_compliant(ComplianceStandard::Soc2, violations, recommendations, &risk_level)
        }
    }
}

impl Default for ComplianceEngine {
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
    fn compliance_standard_roundtrip() {
        for std in ComplianceStandard::ALL {
            let s = std.as_str();
            assert_eq!(ComplianceStandard::from_str_lossy(s), Some(std));
        }
    }

    #[test]
    fn hipaa_phi_without_encryption() {
        let engine = ComplianceEngine::new();
        let config = serde_json::json!({"data_type": "phi", "action": "access"});
        let result = engine.check_standard(ComplianceStandard::Hipaa, "data_access", &config);
        assert!(!result.compliant);
        assert!(result.violations.len() > 0);
        assert_eq!(result.risk_level, "critical");
    }

    #[test]
    fn hipaa_phi_with_encryption_and_audit() {
        let engine = ComplianceEngine::new();
        let config = serde_json::json!({"data_type": "phi", "action": "access", "encryption": "aes_256", "audit": true});
        let result = engine.check_standard(ComplianceStandard::Hipaa, "data_access", &config);
        assert!(result.compliant);
    }

    #[test]
    fn pci_dss_card_without_tokenization() {
        let engine = ComplianceEngine::new();
        let config = serde_json::json!({"data_type": "card_number", "action": "process"});
        let result = engine.check_standard(ComplianceStandard::PciDss, "payment", &config);
        assert!(!result.compliant);
    }

    #[test]
    fn gdpr_personal_data_without_consent() {
        let engine = ComplianceEngine::new();
        let config = serde_json::json!({"data_type": "personal_data", "action": "process"});
        let result = engine.check_standard(ComplianceStandard::Gdpr, "data_process", &config);
        assert!(!result.compliant);
    }

    #[test]
    fn gdpr_personal_data_with_consent() {
        let engine = ComplianceEngine::new();
        let config = serde_json::json!({"data_type": "personal_data", "action": "process", "consent": true});
        let result = engine.check_standard(ComplianceStandard::Gdpr, "data_process", &config);
        assert!(result.compliant);
    }

    #[test]
    fn coppa_children_without_parental_consent() {
        let engine = ComplianceEngine::new();
        let config = serde_json::json!({"data_type": "student_data", "age": "under_13"});
        let result = engine.check_standard(ComplianceStandard::Coppa, "data_collect", &config);
        assert!(!result.compliant);
        assert_eq!(result.risk_level, "critical");
    }

    #[test]
    fn sox_financial_without_dual_control() {
        let engine = ComplianceEngine::new();
        let config = serde_json::json!({"data_type": "financial_report", "action": "modify"});
        let result = engine.check_standard(ComplianceStandard::Sox, "data_modify", &config);
        assert!(!result.compliant);
    }

    #[test]
    fn aml_kyc_without_verification() {
        let engine = ComplianceEngine::new();
        let config = serde_json::json!({"action": "transfer", "amount": "50000"});
        let result = engine.check_standard(ComplianceStandard::AmlKyc, "transaction", &config);
        assert!(!result.compliant);
    }

    #[test]
    fn check_category_returns_correct_standards() {
        let engine = ComplianceEngine::new();
        let config = serde_json::json!({"action": "view"});
        let results = engine.check_category(NicheCategory::HealthTech, "view_data", &config);
        assert_eq!(results.len(), NicheCategory::HealthTech.compliance_standards().len());
    }

    #[test]
    fn compliant_result_display() {
        let result = ComplianceResult::compliant(ComplianceStandard::Gdpr);
        assert!(result.to_string().contains("COMPLIANT"));
    }
}
