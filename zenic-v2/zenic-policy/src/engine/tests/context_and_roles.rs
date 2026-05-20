//! Policy Engine — Test helpers and PolicyContext tests.

use zenic_proto::{BusinessDomain, NodeCriticality, NodeId, SessionId, TenantId};

use crate::permission::{Action, Permission, Resource};
use crate::role::{CriticalityClearance, Role, RoleId, RolePriority};

use super::super::types::PolicyContext;
use super::super::engine_impl::PolicyEngine;

// -----------------------------------------------------------------------
// Test helpers
// -----------------------------------------------------------------------

pub(crate) fn make_admin_role() -> Role {
    let mut role = Role::new("admin", "Administrator")
        .with_priority(RolePriority::Admin)
        .with_clearance(CriticalityClearance::Critical);
    role.add_permission(Permission::new(Action::Admin, Resource::AllNodes));
    role.add_permission(Permission::new(Action::Execute, Resource::AllNodes));
    role.add_permission(Permission::new(Action::Read, Resource::AllNodes));
    role.add_permission(Permission::new(Action::Write, Resource::AllNodes));
    role.add_permission(Permission::new(Action::Delete, Resource::AllNodes));
    role.add_permission(Permission::new(Action::Cancel, Resource::AllWorkflows));
    role.add_permission(Permission::new(Action::ViewAudit, Resource::AuditLog));
    role.add_permission(Permission::new(Action::ManageRoles, Resource::RoleRegistry));
    role
}

pub(crate) fn make_viewer_role() -> Role {
    let mut role = Role::new("viewer", "View-only")
        .with_priority(RolePriority::Viewer)
        .with_clearance(CriticalityClearance::Low);
    role.add_permission(Permission::new(Action::Read, Resource::AllNodes));
    role
}

pub(crate) fn make_operator_role() -> Role {
    let mut role = Role::new("operator", "Standard operator")
        .with_priority(RolePriority::Standard)
        .with_clearance(CriticalityClearance::High);
    role.add_permission(Permission::new(Action::Execute, Resource::AllNodes));
    role.add_permission(Permission::new(Action::Read, Resource::AllNodes));
    role.add_permission(Permission::new(Action::Write, Resource::AllNodes));
    role
}

// -----------------------------------------------------------------------
// PolicyContext tests
// -----------------------------------------------------------------------

#[test]
fn policy_context_new() {
    let ctx = PolicyContext::new(
        SessionId::new(),
        TenantId::new(),
        Permission::new(Action::Execute, Resource::AllNodes),
    );
    assert!(ctx.domain.is_none());
    assert!(ctx.criticality.is_none());
    assert!(ctx.node_id.is_none());
}

#[test]
fn policy_context_with_domain() {
    let ctx = PolicyContext::new(
        SessionId::new(),
        TenantId::new(),
        Permission::new(Action::Execute, Resource::AllNodes),
    )
    .with_domain(BusinessDomain::ECommerce);
    assert_eq!(ctx.domain, Some(BusinessDomain::ECommerce));
}

#[test]
fn policy_context_with_criticality() {
    let node_id = NodeId::new();
    let ctx = PolicyContext::new(
        SessionId::new(),
        TenantId::new(),
        Permission::new(Action::Execute, Resource::AllNodes),
    )
    .with_criticality(NodeCriticality::High, node_id);
    assert_eq!(ctx.criticality, Some(NodeCriticality::High));
    assert_eq!(ctx.node_id, Some(node_id));
}

// -----------------------------------------------------------------------
// PolicyEngine: role management
// -----------------------------------------------------------------------

#[test]
fn engine_register_role() {
    let mut engine = PolicyEngine::new();
    let role = make_admin_role();
    assert!(engine.register_role(role).is_ok());
    assert_eq!(engine.role_count(), 1);
}

#[test]
fn engine_assign_role() {
    let mut engine = PolicyEngine::new();
    let role = make_admin_role();
    let role_id = role.id;
    engine.register_role(role).expect("register");
    let sid = SessionId::new();
    let tid = TenantId::new();
    assert!(engine.assign_role(role_id, sid, tid).is_ok());
    assert_eq!(engine.assignment_count(), 1);
}

#[test]
fn engine_assign_nonexistent_role_fails() {
    let mut engine = PolicyEngine::new();
    let result = engine.assign_role(RoleId::new(), SessionId::new(), TenantId::new());
    assert!(result.is_err());
}

// -----------------------------------------------------------------------
// PolicyEngine: rule and veto management
// -----------------------------------------------------------------------

#[test]
fn engine_add_rule() {
    use crate::rule::PolicyRule;
    let mut engine = PolicyEngine::new();
    let rule = PolicyRule::allow(
        "allow_execute",
        "Allow executing nodes",
        Permission::new(Action::Execute, Resource::AllNodes),
    );
    assert!(engine.add_rule(rule).is_ok());
    assert_eq!(engine.rule_count(), 1);
}

#[test]
fn engine_register_veto() {
    use crate::gate::SafetyVeto;
    let mut engine = PolicyEngine::new();
    let veto = SafetyVeto::new(
        "no_delete_nodes",
        "Never delete nodes",
        Action::Delete,
        Resource::AllNodes,
    );
    assert!(engine.register_veto(veto).is_ok());
    assert_eq!(engine.veto_count(), 1);
}
