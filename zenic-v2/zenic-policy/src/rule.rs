//! Policy rules: allow/deny rules with conditions and priorities.
//!
//! A [`PolicyRule`] defines whether a specific action on a resource
//! is allowed or denied, optionally subject to conditions. Rules are
//! collected in a [`RuleSet`] and evaluated in priority order during
//! policy evaluation.

use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use std::fmt;
use zenic_proto::{BusinessDomain, PolicyId};

use crate::errors::PolicyError;
use crate::permission::{Action, Permission, Resource};

// ---------------------------------------------------------------------------
// RuleEffect
// ---------------------------------------------------------------------------

/// The outcome of a policy rule when it matches.
///
/// Rules can either allow or deny an action. Deny rules take precedence
/// over allow rules in the policy engine (default-deny model).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RuleEffect {
    /// The action is explicitly allowed.
    Allow,
    /// The action is explicitly denied.
    Deny,
}

impl fmt::Display for RuleEffect {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Allow => write!(f, "allow"),
            Self::Deny => write!(f, "deny"),
        }
    }
}

// ---------------------------------------------------------------------------
// RuleCondition
// ---------------------------------------------------------------------------

/// A condition that must be true for a rule to apply.
///
/// Conditions are evaluated at runtime during policy evaluation.
/// A rule with no conditions always applies (unconditional rule).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum RuleCondition {
    /// The action must target a node in the given business domain.
    DomainEquals(BusinessDomain),
    /// The action must target a specific resource (exact match).
    ResourceEquals(Resource),
    /// The action must be one of the specified actions.
    ActionIn(Vec<Action>),
    /// The action must target a resource of a specific type (wildcard).
    ResourceTypeEquals(String),
    /// A combination of conditions that must all be true.
    AllOf(Vec<RuleCondition>),
    /// A combination of conditions where at least one must be true.
    AnyOf(Vec<RuleCondition>),
}

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
// PolicyRule
// ---------------------------------------------------------------------------

/// A single policy rule that can allow or deny an action.
///
/// Rules are evaluated in priority order (higher priority first).
/// When multiple rules match, the one with the highest priority wins.
/// In case of a tie, deny takes precedence over allow (default-deny).
///
/// Rules with no conditions always match (unconditional). Rules with
/// conditions only match when all their conditions are satisfied.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PolicyRule {
    /// Unique identifier for this rule.
    pub id: PolicyId,
    /// Human-readable name (e.g., "allow_execute_nodes").
    pub name: String,
    /// Short description of what this rule does.
    pub description: String,
    /// Whether this rule allows or denies the action.
    pub effect: RuleEffect,
    /// The permission pattern this rule applies to.
    pub target: Permission,
    /// Optional conditions that must be satisfied for this rule to apply.
    pub conditions: Vec<RuleCondition>,
    /// Priority (higher = evaluated first). Rules with equal priority:
    /// Deny wins over Allow.
    pub priority: i32,
}

impl PolicyRule {
    /// Creates a new allow rule.
    pub fn allow(name: &str, description: &str, target: Permission) -> Self {
        Self {
            id: PolicyId::new(),
            name: name.to_string(),
            description: description.to_string(),
            effect: RuleEffect::Allow,
            target,
            conditions: Vec::new(),
            priority: 0,
        }
    }

    /// Creates a new deny rule.
    pub fn deny(name: &str, description: &str, target: Permission) -> Self {
        Self {
            id: PolicyId::new(),
            name: name.to_string(),
            description: description.to_string(),
            effect: RuleEffect::Deny,
            target,
            conditions: Vec::new(),
            priority: 0,
        }
    }

    /// Adds a condition to this rule.
    pub fn with_condition(mut self, condition: RuleCondition) -> Self {
        self.conditions.push(condition);
        self
    }

    /// Sets the priority of this rule.
    pub fn with_priority(mut self, priority: i32) -> Self {
        self.priority = priority;
        self
    }

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

    /// Validates the policy rule for internal consistency.
    pub fn validate(&self) -> Result<(), PolicyError> {
        if self.name.is_empty() {
            return Err(PolicyError::Validation(
                "policy rule name must not be empty".to_string(),
            ));
        }
        if let Err(e) = self.target.validate() {
            return Err(PolicyError::Validation(format!(
                "invalid target permission in rule '{}': {}",
                self.name, e
            )));
        }
        Ok(())
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
    use crate::permission::Action;

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
    fn policy_rule_allow() {
        let rule = PolicyRule::allow(
            "allow_execute",
            "Allow executing nodes",
            Permission::new(Action::Execute, Resource::AllNodes),
        );
        assert_eq!(rule.effect, RuleEffect::Allow);
        assert!(rule.conditions.is_empty());
        assert_eq!(rule.priority, 0);
    }

    #[test]
    fn policy_rule_deny() {
        let rule = PolicyRule::deny(
            "deny_delete",
            "Deny deleting nodes",
            Permission::new(Action::Delete, Resource::AllNodes),
        );
        assert_eq!(rule.effect, RuleEffect::Deny);
    }

    #[test]
    fn policy_rule_with_condition_and_priority() {
        let rule = PolicyRule::allow(
            "allow_ecommerce_execute",
            "Allow execute in ecommerce domain",
            Permission::new(Action::Execute, Resource::AllNodes),
        )
        .with_condition(RuleCondition::DomainEquals(BusinessDomain::ECommerce))
        .with_priority(10);

        assert_eq!(rule.conditions.len(), 1);
        assert_eq!(rule.priority, 10);
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
    fn policy_rule_validate_valid() {
        let rule = PolicyRule::allow("valid", "Valid rule", Permission::new(Action::Execute, Resource::AllNodes));
        assert!(rule.validate().is_ok());
    }

    #[test]
    fn policy_rule_validate_empty_name() {
        let rule = PolicyRule {
            id: PolicyId::new(),
            name: String::new(),
            description: "No name".to_string(),
            effect: RuleEffect::Allow,
            target: Permission::new(Action::Execute, Resource::AllNodes),
            conditions: Vec::new(),
            priority: 0,
        };
        assert!(rule.validate().is_err());
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
