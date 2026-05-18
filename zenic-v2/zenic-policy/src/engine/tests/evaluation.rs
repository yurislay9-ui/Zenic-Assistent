//! Policy Engine — Evaluation and audit tests.

use zenic_proto::{NodeCriticality, NodeId, SessionId, TenantId};

use crate::audit::PolicyDecision;
use crate::gate::{CriticalityGateBuilder, SafetyVeto};
use crate::permission::{Action, Permission, Resource};
use crate::role::CriticalityClearance;
use crate::rule::PolicyRule;

use super::super::engine_impl::PolicyEngine;
use super::super::types::PolicyContext;
use super::context_and_roles::{make_admin_role, make_operator_role, make_viewer_role};

// -----------------------------------------------------------------------
// PolicyEngine: full evaluation — allowed
// -----------------------------------------------------------------------

#[test]
fn engine_evaluate_allowed() {
    let mut engine = PolicyEngine::new();
    let role = make_operator_role();
    let role_id = role.id;
    engine.register_role(role).expect("register");

    let sid = SessionId::new();
    let tid = TenantId::new();
    engine.assign_role(role_id, sid, tid).expect("assign");

    engine
        .add_rule(PolicyRule::allow(
            "allow_execute",
            "Allow execute",
            Permission::new(Action::Execute, Resource::AllNodes),
        ))
        .expect("add rule");

    let ctx = PolicyContext::new(
        sid,
        tid,
        Permission::new(Action::Execute, Resource::AllNodes),
    );

    let result = engine.evaluate(&ctx);
    assert!(result.is_ok());
    assert_eq!(result.unwrap(), PolicyDecision::Allowed);
    assert_eq!(engine.audit_count(), 1);
}

#[test]
fn engine_is_allowed_convenience() {
    let mut engine = PolicyEngine::new();
    let role = make_operator_role();
    let role_id = role.id;
    engine.register_role(role).expect("register");

    let sid = SessionId::new();
    let tid = TenantId::new();
    engine.assign_role(role_id, sid, tid).expect("assign");

    engine
        .add_rule(PolicyRule::allow(
            "allow_execute",
            "Allow execute",
            Permission::new(Action::Execute, Resource::AllNodes),
        ))
        .expect("add rule");

    let ctx = PolicyContext::new(
        sid,
        tid,
        Permission::new(Action::Execute, Resource::AllNodes),
    );

    assert!(engine.is_allowed(&ctx));
}

// -----------------------------------------------------------------------
// PolicyEngine: veto blocks
// -----------------------------------------------------------------------

#[test]
fn engine_evaluate_veto_blocks() {
    let mut engine = PolicyEngine::new();
    let role = make_admin_role();
    let role_id = role.id;
    engine.register_role(role).expect("register");

    let sid = SessionId::new();
    let tid = TenantId::new();
    engine.assign_role(role_id, sid, tid).expect("assign");

    engine
        .add_rule(PolicyRule::allow(
            "allow_delete",
            "Allow delete",
            Permission::new(Action::Delete, Resource::AllNodes),
        ))
        .expect("add rule");

    engine
        .register_veto(SafetyVeto::new(
            "no_delete",
            "Never delete",
            Action::Delete,
            Resource::AllNodes,
        ))
        .expect("register veto");

    let ctx = PolicyContext::new(
        sid,
        tid,
        Permission::new(Action::Delete, Resource::AllNodes),
    );

    let result = engine.evaluate(&ctx);
    assert!(result.is_err());
    assert!(!engine.audit_denials().is_empty());
}

// -----------------------------------------------------------------------
// PolicyEngine: no role denies
// -----------------------------------------------------------------------

#[test]
fn engine_evaluate_no_role_denies() {
    let mut engine = PolicyEngine::new();
    engine
        .add_rule(PolicyRule::allow(
            "allow_execute",
            "Allow execute",
            Permission::new(Action::Execute, Resource::AllNodes),
        ))
        .expect("add rule");

    let ctx = PolicyContext::new(
        SessionId::new(),
        TenantId::new(),
        Permission::new(Action::Execute, Resource::AllNodes),
    );

    let result = engine.evaluate(&ctx);
    assert!(result.is_err());
}

// -----------------------------------------------------------------------
// PolicyEngine: explicit deny rule
// -----------------------------------------------------------------------

#[test]
fn engine_evaluate_explicit_deny_rule() {
    let mut engine = PolicyEngine::new();
    let role = make_operator_role();
    let role_id = role.id;
    engine.register_role(role).expect("register");

    let sid = SessionId::new();
    let tid = TenantId::new();
    engine.assign_role(role_id, sid, tid).expect("assign");

    engine
        .add_rule(PolicyRule::deny(
            "deny_delete",
            "Deny delete",
            Permission::new(Action::Delete, Resource::AllNodes),
        ))
        .expect("add rule");

    let ctx = PolicyContext::new(
        sid,
        tid,
        Permission::new(Action::Delete, Resource::AllNodes),
    );

    let result = engine.evaluate(&ctx);
    assert!(result.is_err());
}

// -----------------------------------------------------------------------
// PolicyEngine: default deny (no rule matches)
// -----------------------------------------------------------------------

#[test]
fn engine_evaluate_default_deny() {
    let mut engine = PolicyEngine::new();
    let role = make_operator_role();
    let role_id = role.id;
    engine.register_role(role).expect("register");

    let sid = SessionId::new();
    let tid = TenantId::new();
    engine.assign_role(role_id, sid, tid).expect("assign");

    // No rule added — should default-deny.
    let ctx = PolicyContext::new(
        sid,
        tid,
        Permission::new(Action::Execute, Resource::AllNodes),
    );

    let result = engine.evaluate(&ctx);
    assert!(result.is_err());
}

// -----------------------------------------------------------------------
// PolicyEngine: criticality gate blocks
// -----------------------------------------------------------------------

#[test]
fn engine_evaluate_criticality_gate_blocks() {
    let mut engine = PolicyEngine::new();
    let role = make_viewer_role(); // Low clearance
    let role_id = role.id;
    engine.register_role(role).expect("register");

    let sid = SessionId::new();
    let tid = TenantId::new();
    engine.assign_role(role_id, sid, tid).expect("assign");

    engine
        .add_rule(PolicyRule::allow(
            "allow_execute",
            "Allow execute",
            Permission::new(Action::Execute, Resource::AllNodes),
        ))
        .expect("add rule");

    let node_id = NodeId::new();
    let ctx = PolicyContext::new(
        sid,
        tid,
        Permission::new(Action::Execute, Resource::Node(node_id)),
    )
    .with_criticality(NodeCriticality::Critical, node_id);

    let result = engine.evaluate(&ctx);
    assert!(result.is_err());
}

#[test]
fn engine_evaluate_criticality_gate_allows_high_clearance() {
    let mut engine = PolicyEngine::new();
    let role = make_operator_role(); // High clearance
    let role_id = role.id;
    engine.register_role(role).expect("register");

    let sid = SessionId::new();
    let tid = TenantId::new();
    engine.assign_role(role_id, sid, tid).expect("assign");

    engine
        .add_rule(PolicyRule::allow(
            "allow_execute",
            "Allow execute",
            Permission::new(Action::Execute, Resource::AllNodes),
        ))
        .expect("add rule");

    let node_id = NodeId::new();
    let ctx = PolicyContext::new(
        sid,
        tid,
        Permission::new(Action::Execute, Resource::Node(node_id)),
    )
    .with_criticality(NodeCriticality::High, node_id);

    let result = engine.evaluate(&ctx);
    assert!(result.is_ok());
}

// -----------------------------------------------------------------------
// PolicyEngine: audit logging
// -----------------------------------------------------------------------

#[test]
fn engine_audit_records_allowed_and_denied() {
    let mut engine = PolicyEngine::new();
    let role = make_operator_role();
    let role_id = role.id;
    engine.register_role(role).expect("register");

    let sid = SessionId::new();
    let tid = TenantId::new();
    engine.assign_role(role_id, sid, tid).expect("assign");

    engine
        .add_rule(PolicyRule::allow(
            "allow_execute",
            "Allow execute",
            Permission::new(Action::Execute, Resource::AllNodes),
        ))
        .expect("add rule");

    // Allowed.
    let ctx_allow = PolicyContext::new(
        sid,
        tid,
        Permission::new(Action::Execute, Resource::AllNodes),
    );
    let _ = engine.evaluate(&ctx_allow);

    // Denied (no permission).
    let ctx_deny = PolicyContext::new(
        sid,
        tid,
        Permission::new(Action::Delete, Resource::AllNodes),
    );
    let _ = engine.evaluate(&ctx_deny);

    assert_eq!(engine.audit_count(), 2);
    assert_eq!(engine.audit_denials().len(), 1);
}

// PolicyEngine: default

#[test]
fn engine_default_is_new() {
    let engine = PolicyEngine::default();
    assert_eq!(engine.role_count(), 0);
    assert_eq!(engine.assignment_count(), 0);
    assert_eq!(engine.rule_count(), 0);
    assert_eq!(engine.veto_count(), 0);
    assert_eq!(engine.audit_count(), 0);
}

// -----------------------------------------------------------------------
// E-12 FIX: replace_criticality_gate test
// -----------------------------------------------------------------------

#[test]
fn engine_replace_criticality_gate_with_builder() {
    let mut engine = PolicyEngine::new();

    // Default gate: Low clearance can access Low criticality.
    assert_eq!(engine.required_clearance(NodeCriticality::Low), CriticalityClearance::Low);

    // Replace with a stricter gate: require Critical clearance even for Low criticality.
    let strict_gate = CriticalityGateBuilder::new()
        .threshold(NodeCriticality::Low, CriticalityClearance::Critical)
        .threshold(NodeCriticality::Medium, CriticalityClearance::Critical)
        .threshold(NodeCriticality::High, CriticalityClearance::Critical)
        .threshold(NodeCriticality::Critical, CriticalityClearance::Critical)
        .build();

    engine.replace_criticality_gate(strict_gate);

    // Now Low criticality requires Critical clearance.
    assert_eq!(engine.required_clearance(NodeCriticality::Low), CriticalityClearance::Critical);

    // Verify that a Low-clearance role is now denied for Low-criticality nodes.
    let role = make_viewer_role(); // Low clearance
    let role_id = role.id;
    engine.register_role(role).expect("register");
    let sid = SessionId::new();
    let tid = TenantId::new();
    engine.assign_role(role_id, sid, tid).expect("assign");
    engine.add_rule(PolicyRule::allow("allow_exec", "Allow", Permission::new(Action::Execute, Resource::AllNodes))).expect("add rule");
    let node_id = NodeId::new();
    let ctx = PolicyContext::new(sid, tid, Permission::new(Action::Execute, Resource::Node(node_id)))
        .with_criticality(NodeCriticality::Low, node_id);
    // Should be denied because even Low criticality now requires Critical clearance.
    assert!(engine.evaluate(&ctx).is_err());
}
