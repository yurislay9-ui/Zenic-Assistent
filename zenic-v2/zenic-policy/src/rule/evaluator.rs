//! Policy rule evaluation: condition checking, rule matching, and rule set logic.

use indexmap::IndexMap;
use zenic_proto::{BusinessDomain, PolicyId};

use crate::errors::PolicyError;
use crate::permission::Permission;

use super::definition::PolicyRule;
use super::types::{RuleCondition, RuleEffect};

// ---------------------------------------------------------------------------
// RuleCondition::evaluate
// ---------------------------------------------------------------------------

impl RuleCondition {
    /// Evaluates whether this condition is satisfied for the given
    /// permission and optional domain context.
    pub fn evaluate(&self, permission: &Permission, domain: Option<BusinessDomain>) -> bool {
        match self {
            Self::DomainEquals(required) => {
                domain == Some(*required)
            }
            Self::ResourceEquals(required) => &permission.resource == required,
            Self::ActionIn(actions) => actions.contains(&permission.action),
            Self::ResourceTypeEquals(type_name) => {
                permission.resource.type_name() == type_name.as_str()
            }
            Self::AllOf(conditions) => conditions
                .iter()
                .all(|c| c.evaluate(permission, domain)),
            Self::AnyOf(conditions) => conditions
                .iter()
                .any(|c| c.evaluate(permission, domain)),
        }
    }
}

// ---------------------------------------------------------------------------
// PolicyRule::matches
// ---------------------------------------------------------------------------

impl PolicyRule {
    /// Whether this rule matches the given permission and domain context.
    ///
    /// A rule matches when:
    /// 1. The rule's target permission implies the requested permission.
    /// 2. All conditions (if any) are satisfied.
    pub fn matches(&self, permission: &Permission, domain: Option<BusinessDomain>) -> bool {
        // Check if the target implies the requested permission.
        if !self.target.implies(permission) {
            return false;
        }
        // Check all conditions.
        self.conditions.iter().all(|c| c.evaluate(permission, domain))
    }
}

// ---------------------------------------------------------------------------
// RuleSet
// ---------------------------------------------------------------------------

/// A collection of policy rules evaluated in priority order.
///
/// The rule set is the primary policy evaluation structure. It contains
/// both allow and deny rules. During evaluation, rules are sorted by
/// priority (descending), and the first matching rule determines the
/// outcome. If no rule matches, the default is deny.
pub struct RuleSet {
    rules: IndexMap<PolicyId, PolicyRule>,
}

impl RuleSet {
    /// Creates an empty rule set.
    pub fn new() -> Self {
        Self {
            rules: IndexMap::new(),
        }
    }

    /// Adds a rule to the set.
    ///
    /// Returns an error if a rule with the same ID already exists.
    pub fn add(&mut self, rule: PolicyRule) -> Result<(), PolicyError> {
        rule.validate()?;
        if self.rules.contains_key(&rule.id) {
            return Err(PolicyError::DuplicateRule(rule.id));
        }
        self.rules.insert(rule.id, rule);
        Ok(())
    }

    /// Returns the rule with the given ID, if it exists.
    pub fn get(&self, id: &PolicyId) -> Option<&PolicyRule> {
        self.rules.get(id)
    }

    /// Whether a rule with the given ID exists.
    pub fn contains(&self, id: &PolicyId) -> bool {
        self.rules.contains_key(id)
    }

    /// Returns the number of rules in the set.
    pub fn len(&self) -> usize {
        self.rules.len()
    }

    /// Whether the rule set is empty.
    pub fn is_empty(&self) -> bool {
        self.rules.is_empty()
    }

    /// Evaluates the rule set against the given permission.
    ///
    /// Rules are evaluated in priority order (highest first).
    /// If multiple rules match at the same priority, Deny wins.
    /// If no rule matches, returns `None` (default-deny).
    pub fn evaluate(&self, permission: &Permission, domain: Option<BusinessDomain>) -> Option<RuleEffect> {
        let mut matching_rules: Vec<&PolicyRule> = self
            .rules
            .values()
            .filter(|r| r.matches(permission, domain))
            .collect();

        // Sort by priority descending (highest priority first).
        matching_rules.sort_by(|a, b| b.priority.cmp(&a.priority));

        let highest_priority = matching_rules.first().map(|r| r.priority)?;

        // Among rules with the highest priority, Deny wins.
        let highest_rules: Vec<&&PolicyRule> = matching_rules
            .iter()
            .filter(|r| r.priority == highest_priority)
            .collect();

        // If any deny rule at the highest priority, deny.
        let has_deny = highest_rules.iter().any(|r| r.effect == RuleEffect::Deny);
        if has_deny {
            return Some(RuleEffect::Deny);
        }

        // Otherwise, the effect of the first rule (which must be Allow).
        highest_rules.first().map(|r| r.effect)
    }

    /// Returns an iterator over all rules in the set.
    pub fn iter(&self) -> impl Iterator<Item = (&PolicyId, &PolicyRule)> {
        self.rules.iter()
    }
}

impl Default for RuleSet {
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
    use crate::permission::{Action, Resource};
    use crate::rule::types::RuleCondition;

    #[test]
    fn rule_effect_display() {
        assert_eq!(RuleEffect::Allow.to_string(), "allow");
        assert_eq!(RuleEffect::Deny.to_string(), "deny");
    }

    #[test]
    fn rule_condition_domain_equals() {
        let condition = RuleCondition::DomainEquals(BusinessDomain::ECommerce);
        let perm = Permission::new(Action::Execute, Resource::AllNodes);
        assert!(condition.evaluate(&perm, Some(BusinessDomain::ECommerce)));
        assert!(!condition.evaluate(&perm, Some(BusinessDomain::Healthcare)));
        assert!(!condition.evaluate(&perm, None));
    }

    #[test]
    fn rule_condition_resource_equals() {
        let node_id = zenic_proto::NodeId::new();
        let condition = RuleCondition::ResourceEquals(Resource::Node(node_id));
        let matching = Permission::new(Action::Execute, Resource::Node(node_id));
        let non_matching = Permission::new(Action::Execute, Resource::AllNodes);
        assert!(condition.evaluate(&matching, None));
        assert!(!condition.evaluate(&non_matching, None));
    }

    #[test]
    fn rule_condition_action_in() {
        let condition = RuleCondition::ActionIn(vec![Action::Execute, Action::Read]);
        let execute_perm = Permission::new(Action::Execute, Resource::AllNodes);
        let write_perm = Permission::new(Action::Write, Resource::AllNodes);
        assert!(condition.evaluate(&execute_perm, None));
        assert!(!condition.evaluate(&write_perm, None));
    }

    #[test]
    fn rule_condition_resource_type_equals() {
        let condition = RuleCondition::ResourceTypeEquals("node".to_string());
        let node_perm = Permission::new(Action::Read, Resource::AllNodes);
        let sg_perm = Permission::new(Action::Read, Resource::AllSubGraphs);
        assert!(condition.evaluate(&node_perm, None));
        assert!(!condition.evaluate(&sg_perm, None));
    }

    #[test]
    fn rule_condition_all_of() {
        let condition = RuleCondition::AllOf(vec![
            RuleCondition::DomainEquals(BusinessDomain::ECommerce),
            RuleCondition::ActionIn(vec![Action::Execute]),
        ]);
        let perm = Permission::new(Action::Execute, Resource::AllNodes);
        assert!(condition.evaluate(&perm, Some(BusinessDomain::ECommerce)));
        assert!(!condition.evaluate(&perm, Some(BusinessDomain::Healthcare)));
        assert!(!condition.evaluate(
            &Permission::new(Action::Write, Resource::AllNodes),
            Some(BusinessDomain::ECommerce),
        ));
    }

    #[test]
    fn rule_condition_any_of() {
        let condition = RuleCondition::AnyOf(vec![
            RuleCondition::DomainEquals(BusinessDomain::ECommerce),
            RuleCondition::DomainEquals(BusinessDomain::Healthcare),
        ]);
        let perm = Permission::new(Action::Execute, Resource::AllNodes);
        assert!(condition.evaluate(&perm, Some(BusinessDomain::ECommerce)));
        assert!(condition.evaluate(&perm, Some(BusinessDomain::Healthcare)));
        assert!(!condition.evaluate(&perm, Some(BusinessDomain::Finance)));
    }

    #[test]
    fn policy_rule_matches_unconditional() {
        let rule = PolicyRule::allow(
            "allow_execute",
            "Allow executing nodes",
            Permission::new(Action::Execute, Resource::AllNodes),
        );
        let specific = Permission::new(Action::Execute, Resource::Node(zenic_proto::NodeId::new()));
        assert!(rule.matches(&specific, None));
    }

    #[test]
    fn policy_rule_matches_with_condition() {
        let rule = PolicyRule::allow(
            "allow_ecommerce",
            "Allow in ecommerce",
            Permission::new(Action::Execute, Resource::AllNodes),
        )
        .with_condition(RuleCondition::DomainEquals(BusinessDomain::ECommerce));

        let perm = Permission::new(Action::Execute, Resource::AllNodes);
        assert!(rule.matches(&perm, Some(BusinessDomain::ECommerce)));
        assert!(!rule.matches(&perm, Some(BusinessDomain::Healthcare)));
    }

    #[test]
    fn policy_rule_does_not_match_different_action() {
        let rule = PolicyRule::allow(
            "allow_execute",
            "Allow executing",
            Permission::new(Action::Execute, Resource::AllNodes),
        );
        let write_perm = Permission::new(Action::Write, Resource::AllNodes);
        assert!(!rule.matches(&write_perm, None));
    }

    #[test]
    fn rule_set_add_and_get() {
        let mut set = RuleSet::new();
        let rule = PolicyRule::allow("test", "Test rule", Permission::new(Action::Execute, Resource::AllNodes));
        let id = rule.id;
        set.add(rule).expect("add");
        assert_eq!(set.len(), 1);
        assert!(set.contains(&id));
    }

    #[test]
    fn rule_set_duplicate_fails() {
        let mut set = RuleSet::new();
        let rule = PolicyRule::allow("test", "Test", Permission::new(Action::Execute, Resource::AllNodes));
        let id = rule.id;
        set.add(rule).expect("add");
        let duplicate = PolicyRule {
            id,
            name: "duplicate".to_string(),
            description: "Duplicate".to_string(),
            effect: RuleEffect::Deny,
            target: Permission::new(Action::Delete, Resource::AllNodes),
            conditions: Vec::new(),
            priority: 0,
        };
        assert!(set.add(duplicate).is_err());
    }

    #[test]
    fn rule_set_evaluate_allow() {
        let mut set = RuleSet::new();
        set.add(PolicyRule::allow(
            "allow_execute",
            "Allow execute",
            Permission::new(Action::Execute, Resource::AllNodes),
        )).expect("add");

        let perm = Permission::new(Action::Execute, Resource::Node(zenic_proto::NodeId::new()));
        let result = set.evaluate(&perm, None);
        assert_eq!(result, Some(RuleEffect::Allow));
    }

    #[test]
    fn rule_set_evaluate_deny_wins_same_priority() {
        let mut set = RuleSet::new();
        set.add(PolicyRule::allow(
            "allow_execute",
            "Allow execute",
            Permission::new(Action::Execute, Resource::AllNodes),
        )).expect("add");
        set.add(PolicyRule::deny(
            "deny_execute",
            "Deny execute",
            Permission::new(Action::Execute, Resource::AllNodes),
        )).expect("add");

        let perm = Permission::new(Action::Execute, Resource::AllNodes);
        let result = set.evaluate(&perm, None);
        assert_eq!(result, Some(RuleEffect::Deny));
    }

    #[test]
    fn rule_set_evaluate_higher_priority_wins() {
        let mut set = RuleSet::new();
        set.add(PolicyRule::allow(
            "allow_execute_high",
            "High priority allow",
            Permission::new(Action::Execute, Resource::AllNodes),
        ).with_priority(10)).expect("add");
        set.add(PolicyRule::deny(
            "deny_execute_low",
            "Low priority deny",
            Permission::new(Action::Execute, Resource::AllNodes),
        ).with_priority(5)).expect("add");

        let perm = Permission::new(Action::Execute, Resource::AllNodes);
        let result = set.evaluate(&perm, None);
        assert_eq!(result, Some(RuleEffect::Allow));
    }

    #[test]
    fn rule_set_evaluate_no_match_returns_none() {
        let set = RuleSet::new();
        let perm = Permission::new(Action::Execute, Resource::AllNodes);
        let result = set.evaluate(&perm, None);
        assert_eq!(result, None);
    }

    #[test]
    fn rule_set_default_is_new() {
        let set = RuleSet::default();
        assert!(set.is_empty());
    }
}
