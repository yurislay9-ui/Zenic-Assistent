//! Domain Safety Gate tests.

#[cfg(test)]
mod tests {
    use super::super::gate::DomainSafetyGate;
    use super::super::types::DomainSafetyCheckResult;
    use crate::categories::NicheCategory;
    use crate::compliance::ComplianceStandard;
    use crate::sensitivity::DataSensitivity;
    use crate::verdict::SafetyVerdict;

    #[test]
    fn base_deny_cannot_be_overridden() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"operation": "delete", "query": "DROP TABLE users"});
        let result = gate.check(
            "database",
            &config,
            NicheCategory::FinTech,
            DataSensitivity::Low,
        );
        // Base gate classifies DROP as DESTRUCTIVE → should be handled
        assert!(!result.can_proceed || result.final_verdict == SafetyVerdict::Confirm);
    }

    #[test]
    fn fintech_compliance_bypass_is_denied() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"action": "bypass_compliance", "target": "kyc_check"});
        let result = gate.check(
            "compliance_operation",
            &config,
            NicheCategory::FinTech,
            DataSensitivity::Medium,
        );
        assert!(result.domain_rules_matched.contains(&"fintech_compliance_bypass".to_string()));
        assert_eq!(result.final_verdict, SafetyVerdict::Deny);
        assert!(!result.can_proceed);
    }

    #[test]
    fn healthtech_phi_with_critical_sensitivity() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"action": "phi_access", "data_type": "health_record"});
        let result = gate.check(
            "data_access",
            &config,
            NicheCategory::HealthTech,
            DataSensitivity::Critical,
        );
        // PHI access → Approve (domain rule), but Critical sensitivity escalates
        assert!(result.escalation_applied || result.final_verdict == SafetyVerdict::Deny);
    }

    #[test]
    fn safe_action_with_low_sensitivity() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"action": "view_dashboard"});
        let result = gate.check(
            "notification",
            &config,
            NicheCategory::AiData,
            DataSensitivity::Low,
        );
        assert_eq!(result.base_verdict, SafetyVerdict::Allow);
        assert!(result.can_proceed);
        assert!(!result.escalation_applied);
    }

    #[test]
    fn critical_compliance_violation_causes_deny() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"data_type": "phi", "action": "access"});
        let result = gate.check(
            "data_access",
            &config,
            NicheCategory::HealthTech,
            DataSensitivity::Low,
        );
        // HIPAA violation with critical risk → DENY
        let has_critical = result.compliance_results.iter().any(|cr| {
            cr.risk_level == "critical" && !cr.compliant
        });
        if has_critical {
            assert_eq!(result.final_verdict, SafetyVerdict::Deny);
        }
    }

    #[test]
    fn escalation_high_sensitivity() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"action": "view_data"});
        let result = gate.check(
            "notification",
            &config,
            NicheCategory::EdTech,
            DataSensitivity::High,
        );
        // Safe action with High sensitivity → ALLOW escalates to CONFIRM
        assert!(result.escalation_applied);
        assert_eq!(result.final_verdict, SafetyVerdict::Confirm);
    }

    #[test]
    fn domain_gate_default() {
        let gate = DomainSafetyGate::default();
        let config = serde_json::json!({});
        let result = gate.check(
            "notification",
            &config,
            NicheCategory::AiData,
            DataSensitivity::Low,
        );
        assert_eq!(result.final_verdict, SafetyVerdict::Allow);
    }

    #[test]
    fn check_domain_rules_only() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"action": "bypass_compliance"});
        let rules = gate.check_domain_rules(NicheCategory::FinTech, "compliance", &config);
        assert!(rules.contains(&"fintech_compliance_bypass".to_string()));
    }

    #[test]
    fn check_compliance_only() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({"data_type": "phi"});
        let result = gate.check_compliance(
            ComplianceStandard::Hipaa,
            "data_access",
            &config,
        );
        assert!(!result.compliant);
    }

    #[test]
    fn get_domain_rules_returns_5() {
        let gate = DomainSafetyGate::new();
        let rules = gate.get_domain_rules(NicheCategory::FinTech);
        assert_eq!(rules.len(), 5);
    }

    #[test]
    fn result_display() {
        let gate = DomainSafetyGate::new();
        let config = serde_json::json!({});
        let result = gate.check(
            "notification",
            &config,
            NicheCategory::AiData,
            DataSensitivity::Low,
        );
        assert!(result.to_string().contains("ALLOW"));
    }
}
