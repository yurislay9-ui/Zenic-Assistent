//! Policy rule tests.

#[cfg(test)]
mod tests {
    use super::super::types::{PolicyRule, RuleCondition, RuleEffect, RuleSet};
    use crate::permission::{Action, Resource};
    use zenic_proto::{BusinessDomain, NodeId, PolicyId};

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
        let node_id = NodeId::new();
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
        let specific = Permission::new(Action::Execute, Resource::Node(NodeId::new()));
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

        let perm = Permission::new(Action::Execute, Resource::Node(NodeId::new()));
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
