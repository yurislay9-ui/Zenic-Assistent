//! Policy rule definition: struct, constructors, and validation.

use serde::{Deserialize, Serialize};
use zenic_proto::PolicyId;

use crate::errors::PolicyError;
use crate::permission::Permission;

use super::types::RuleCondition;
use super::types::RuleEffect;

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
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::permission::{Action, Resource};

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
        .with_condition(RuleCondition::DomainEquals(zenic_proto::BusinessDomain::ECommerce))
        .with_priority(10);

        assert_eq!(rule.conditions.len(), 1);
        assert_eq!(rule.priority, 10);
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
}
