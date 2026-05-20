//! Domain rule evaluator — DomainRuleSet with query and check methods.

use crate::categories::NicheCategory;

use super::loader::build_all_rules;
use super::types::DomainRule;

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
            rules: build_all_rules(),
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
    use crate::verdict::SafetyVerdict;

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
