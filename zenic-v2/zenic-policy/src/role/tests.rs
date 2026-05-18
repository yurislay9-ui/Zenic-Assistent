//! Role tests.

#[cfg(test)]
mod tests {
    use super::*;
    use crate::permission::{Action, Permission, Resource};
    use std::str::FromStr;
    use zenic_proto::{NodeCriticality, NodeId, SessionId, TenantId};

    #[test]
    fn role_id_display_roundtrip() {
        let id = RoleId::new();
        let s = id.to_string();
        let parsed: RoleId = s.parse().expect("valid parse");
        assert_eq!(id, parsed);
    }

    #[test]
    fn role_id_default_generates_unique() {
        let a = RoleId::default();
        let b = RoleId::default();
        assert_ne!(a, b);
    }

    #[test]
    fn role_id_invalid_parse() {
        let result = RoleId::from_str("not-a-uuid");
        assert!(result.is_err());
    }

    #[test]
    fn role_priority_ordering() {
        assert!(RolePriority::Admin > RolePriority::Elevated);
        assert!(RolePriority::Elevated > RolePriority::Standard);
        assert!(RolePriority::Standard > RolePriority::Viewer);
    }

    #[test]
    fn role_priority_display() {
        assert_eq!(RolePriority::Admin.to_string(), "admin");
        assert_eq!(RolePriority::Viewer.to_string(), "viewer");
    }

    #[test]
    fn criticality_clearance_allows() {
        assert!(CriticalityClearance::Critical.allows(NodeCriticality::Critical));
        assert!(CriticalityClearance::Critical.allows(NodeCriticality::Low));
        assert!(CriticalityClearance::High.allows(NodeCriticality::High));
        assert!(!CriticalityClearance::High.allows(NodeCriticality::Critical));
        assert!(CriticalityClearance::Medium.allows(NodeCriticality::Medium));
        assert!(!CriticalityClearance::Medium.allows(NodeCriticality::High));
        assert!(CriticalityClearance::Low.allows(NodeCriticality::Low));
        assert!(!CriticalityClearance::Low.allows(NodeCriticality::Medium));
    }

    #[test]
    fn criticality_clearance_as_criticality() {
        assert_eq!(CriticalityClearance::Critical.as_criticality(), NodeCriticality::Critical);
        assert_eq!(CriticalityClearance::High.as_criticality(), NodeCriticality::High);
    }

    #[test]
    fn role_new() {
        let role = Role::new("operator", "Standard operator role");
        assert_eq!(role.name, "operator");
        assert!(role.permissions.is_empty());
        assert_eq!(role.priority, RolePriority::Standard);
        assert_eq!(role.criticality_clearance, CriticalityClearance::Medium);
    }

    #[test]
    fn role_add_permission() {
        let mut role = Role::new("admin", "Administrator");
        role.add_permission(Permission::new(Action::Admin, Resource::AllNodes));
        assert_eq!(role.permission_count(), 1);
    }

    #[test]
    fn role_add_duplicate_permission_ignored() {
        let mut role = Role::new("admin", "Administrator");
        let perm = Permission::new(Action::Admin, Resource::AllNodes);
        role.add_permission(perm.clone());
        role.add_permission(perm);
        assert_eq!(role.permission_count(), 1);
    }

    #[test]
    fn role_with_priority_and_clearance() {
        let role = Role::new("super_admin", "Super administrator")
            .with_priority(RolePriority::Admin)
            .with_clearance(CriticalityClearance::Critical);
        assert_eq!(role.priority, RolePriority::Admin);
        assert_eq!(role.criticality_clearance, CriticalityClearance::Critical);
    }

    #[test]
    fn role_implies_permission_wildcard() {
        let mut role = Role::new("executor", "Can execute any node");
        role.add_permission(Permission::new(Action::Execute, Resource::AllNodes));
        let specific = Permission::new(Action::Execute, Resource::Node(NodeId::new()));
        assert!(role.implies_permission(&specific));
    }

    #[test]
    fn role_does_not_imply_different_action() {
        let mut role = Role::new("reader", "Can read any node");
        role.add_permission(Permission::new(Action::Read, Resource::AllNodes));
        let execute_perm = Permission::new(Action::Execute, Resource::Node(NodeId::new()));
        assert!(!role.implies_permission(&execute_perm));
    }

    #[test]
    fn role_allows_criticality() {
        let role = Role::new("high_role", "High clearance")
            .with_clearance(CriticalityClearance::High);
        assert!(role.allows_criticality(NodeCriticality::High));
        assert!(!role.allows_criticality(NodeCriticality::Critical));
    }

    #[test]
    fn role_validate_valid() {
        let role = Role::new("valid_role", "A valid role");
        assert!(role.validate().is_ok());
    }

    #[test]
    fn role_validate_empty_name() {
        let role = Role {
            id: RoleId::new(),
            name: String::new(),
            description: "No name".to_string(),
            permissions: Vec::new(),
            priority: RolePriority::Standard,
            criticality_clearance: CriticalityClearance::Medium,
        };
        assert!(role.validate().is_err());
    }

    #[test]
    fn role_validate_space_in_name() {
        let role = Role {
            id: RoleId::new(),
            name: "has space".to_string(),
            description: "Bad name".to_string(),
            permissions: Vec::new(),
            priority: RolePriority::Standard,
            criticality_clearance: CriticalityClearance::Medium,
        };
        assert!(role.validate().is_err());
    }

    #[test]
    fn role_assignment_new() {
        let assignment = RoleAssignment::new(RoleId::new(), SessionId::new(), TenantId::new());
        assert_eq!(assignment.role_id, assignment.role_id);
    }

    #[test]
    fn role_registry_register_and_get() {
        let mut registry = RoleRegistry::new();
        let role = Role::new("viewer", "View-only role");
        let id = role.id;
        registry.register(role).expect("register");
        assert_eq!(registry.len(), 1);
        assert!(registry.contains(&id));
        assert!(registry.get(&id).is_some());
    }

    #[test]
    fn role_registry_duplicate_fails() {
        let mut registry = RoleRegistry::new();
        let role = Role::new("viewer", "View-only role");
        let id = role.id;
        registry.register(role).expect("register");
        let duplicate = Role {
            id,
            name: "duplicate".to_string(),
            description: "Duplicate ID".to_string(),
            permissions: Vec::new(),
            priority: RolePriority::Standard,
            criticality_clearance: CriticalityClearance::Medium,
        };
        let result = registry.register(duplicate);
        assert!(result.is_err());
    }

    #[test]
    fn role_registry_default_is_new() {
        let registry = RoleRegistry::default();
        assert!(registry.is_empty());
    }

    #[test]
    fn role_registry_roles_for_session() {
        let mut registry = RoleRegistry::new();
        let role1 = Role::new("viewer", "View-only");
        let role2 = Role::new("editor", "Edit access");
        let rid1 = role1.id;
        let rid2 = role2.id;
        registry.register(role1).expect("register");
        registry.register(role2).expect("register");

        let sid = SessionId::new();
        let tid = TenantId::new();
        let assignments = vec![
            RoleAssignment::new(rid1, sid, tid),
            RoleAssignment::new(rid2, sid, tid),
        ];

        let roles = registry.roles_for_session(&assignments, &sid, &tid);
        assert_eq!(roles.len(), 2);
    }

    #[test]
    fn role_registry_roles_for_session_different_tenant() {
        let mut registry = RoleRegistry::new();
        let role = Role::new("viewer", "View-only");
        let rid = role.id;
        registry.register(role).expect("register");

        let sid = SessionId::new();
        let tid1 = TenantId::new();
        let tid2 = TenantId::new();
        let assignments = vec![RoleAssignment::new(rid, sid, tid1)];

        let roles = registry.roles_for_session(&assignments, &sid, &tid2);
        assert!(roles.is_empty());
    }
}
