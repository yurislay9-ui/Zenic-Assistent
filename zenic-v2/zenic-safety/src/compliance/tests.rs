//! Compliance module tests.

#[cfg(test)]
mod tests {
    use super::super::types::{ComplianceResult, ComplianceStandard};
    use super::super::engine_impl::ComplianceEngine;
    use crate::categories::NicheCategory;

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
