//! Gate module tests.

#[cfg(test)]
mod tests {
    use super::super::types::{CriticalityGate, CriticalityGateBuilder, SafetyVeto, SafetyVetoRegistry};
    use crate::permission::{Action, Permission, Resource};
    use crate::role::{CriticalityClearance, Role};
    use zenic_proto::{NodeCriticality, NodeId, SessionId};

    #[test]
    fn criticality_gate_default_allows_matching() {
        let gate = CriticalityGate::new();
        let role = Role::new("admin", "Admin role")
            .with_clearance(CriticalityClearance::Critical);
        let roles = vec![&role];
        let result = gate.check(
            &roles,
            NodeCriticality::Critical,
            SessionId::new(),
            NodeId::new(),
        );
        assert!(result.is_ok());
    }

    #[test]
    fn criticality_gate_denies_insufficient_clearance() {
        let gate = CriticalityGate::new();
        let role = Role::new("viewer", "Viewer role")
            .with_clearance(CriticalityClearance::Low);
        let roles = vec![&role];
        let result = gate.check(
            &roles,
            NodeCriticality::Critical,
            SessionId::new(),
            NodeId::new(),
        );
        assert!(result.is_err());
    }

    #[test]
    fn criticality_gate_uses_highest_clearance() {
        let gate = CriticalityGate::new();
        let low_role = Role::new("viewer", "Viewer").with_clearance(CriticalityClearance::Low);
        let admin_role = Role::new("admin", "Admin").with_clearance(CriticalityClearance::Critical);
        let roles = vec![&low_role, &admin_role];
        let result = gate.check(
            &roles,
            NodeCriticality::High,
            SessionId::new(),
            NodeId::new(),
        );
        assert!(result.is_ok());
    }

    #[test]
    fn criticality_gate_no_roles_denies() {
        let gate = CriticalityGate::new();
        let roles: Vec<&Role> = vec![];
        let result = gate.check(
            &roles,
            NodeCriticality::Low,
            SessionId::new(),
            NodeId::new(),
        );
        assert!(result.is_err());
    }

    #[test]
    fn criticality_gate_custom_threshold() {
        let gate = CriticalityGateBuilder::new()
            .threshold(NodeCriticality::Low, CriticalityClearance::Critical)
            .build();
        let medium_role = Role::new("operator", "Operator").with_clearance(CriticalityClearance::Medium);
        let roles = vec![&medium_role];
        let result = gate.check(
            &roles,
            NodeCriticality::Low,
            SessionId::new(),
            NodeId::new(),
        );
        assert!(result.is_err());
    }

    #[test]
    fn criticality_gate_default_is_new() {
        let gate = CriticalityGate::default();
        let role = Role::new("admin", "Admin").with_clearance(CriticalityClearance::Critical);
        let roles = vec![&role];
        let result = gate.check(&roles, NodeCriticality::Low, SessionId::new(), NodeId::new());
        assert!(result.is_ok());
    }

    #[test]
    fn safety_veto_new() {
        let veto = SafetyVeto::new(
            "no_delete_critical",
            "Never allow deleting critical nodes",
            Action::Delete,
            Resource::AllNodes,
        );
        assert_eq!(veto.name, "no_delete_critical");
        assert_eq!(veto.blocked_action, Action::Delete);
    }

    #[test]
    fn safety_veto_blocks_matching() {
        let veto = SafetyVeto::new(
            "no_delete_nodes",
            "No deleting nodes",
            Action::Delete,
            Resource::AllNodes,
        );
        let specific = Permission::new(Action::Delete, Resource::Node(NodeId::new()));
        assert!(veto.blocks(&specific));
    }

    #[test]
    fn safety_veto_does_not_block_different_action() {
        let veto = SafetyVeto::new(
            "no_delete_nodes",
            "No deleting nodes",
            Action::Delete,
            Resource::AllNodes,
        );
        let execute = Permission::new(Action::Execute, Resource::Node(NodeId::new()));
        assert!(!veto.blocks(&execute));
    }

    #[test]
    fn safety_veto_does_not_block_different_resource() {
        let veto = SafetyVeto::new(
            "no_delete_nodes",
            "No deleting nodes",
            Action::Delete,
            Resource::AllNodes,
        );
        let delete_workflow = Permission::new(Action::Delete, Resource::AllWorkflows);
        assert!(!veto.blocks(&delete_workflow));
    }

    #[test]
    fn safety_veto_validate_valid() {
        let veto = SafetyVeto::new("valid", "Valid veto", Action::Delete, Resource::AllNodes);
        assert!(veto.validate().is_ok());
    }

    #[test]
    fn safety_veto_validate_empty_name() {
        let veto = SafetyVeto {
            name: String::new(),
            description: "No name".to_string(),
            blocked_action: Action::Delete,
            blocked_resource: Resource::AllNodes,
        };
        assert!(veto.validate().is_err());
    }

    #[test]
    fn safety_veto_display() {
        let veto = SafetyVeto::new("test", "Test", Action::Delete, Resource::AllNodes);
        let display = veto.to_string();
        assert!(display.contains("delete"));
        assert!(display.contains("all_nodes"));
    }

    #[test]
    fn veto_registry_register_and_check() {
        let mut registry = SafetyVetoRegistry::new();
        registry
            .register(SafetyVeto::new(
                "no_delete_nodes",
                "No deleting",
                Action::Delete,
                Resource::AllNodes,
            ))
            .expect("register");

        assert_eq!(registry.len(), 1);
        let blocked = Permission::new(Action::Delete, Resource::Node(NodeId::new()));
        assert!(registry.is_blocked(&blocked));

        let allowed = Permission::new(Action::Execute, Resource::Node(NodeId::new()));
        assert!(!registry.is_blocked(&allowed));
    }

    #[test]
    fn veto_registry_duplicate_name_fails() {
        let mut registry = SafetyVetoRegistry::new();
        registry
            .register(SafetyVeto::new("no_delete", "No delete", Action::Delete, Resource::AllNodes))
            .expect("register");
        let result = registry.register(SafetyVeto::new("no_delete", "Duplicate", Action::Delete, Resource::AllNodes));
        assert!(result.is_err());
    }

    #[test]
    fn veto_registry_blocking_veto_returns_veto() {
        let mut registry = SafetyVetoRegistry::new();
        registry
            .register(SafetyVeto::new("no_delete", "No delete", Action::Delete, Resource::AllNodes))
            .expect("register");

        let perm = Permission::new(Action::Delete, Resource::Node(NodeId::new()));
        let blocking = registry.blocking_veto(&perm);
        assert!(blocking.is_some());
        assert_eq!(blocking.unwrap().name, "no_delete");
    }

    #[test]
    fn veto_registry_no_blocking_veto() {
        let registry = SafetyVetoRegistry::new();
        let perm = Permission::new(Action::Execute, Resource::AllNodes);
        assert!(registry.blocking_veto(&perm).is_none());
    }

    #[test]
    fn veto_registry_default_is_new() {
        let registry = SafetyVetoRegistry::default();
        assert!(registry.is_empty());
    }
}
