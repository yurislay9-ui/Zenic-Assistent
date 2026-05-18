//! Policy engine management methods: role, rule, veto, gate, and audit operations.

use zenic_proto::{NodeCriticality, SessionId, TenantId};

use crate::errors::PolicyError;
use crate::gate::{CriticalityGate, SafetyVeto};
use crate::role::{CriticalityClearance, Role, RoleAssignment, RoleId};

use super::evaluator::PolicyEngine;

// ---------------------------------------------------------------------------
// PolicyEngine management methods
// ---------------------------------------------------------------------------

impl PolicyEngine {
    // -----------------------------------------------------------------------
    // Role management
    // -----------------------------------------------------------------------

    /// Registers a role in the engine.
    pub fn register_role(&mut self, role: Role) -> Result<(), PolicyError> {
        self.role_registry.register(role)
    }

    /// Assigns a role to a session within a tenant.
    pub fn assign_role(
        &mut self,
        role_id: RoleId,
        session_id: SessionId,
        tenant_id: TenantId,
    ) -> Result<(), PolicyError> {
        if !self.role_registry.contains(&role_id) {
            return Err(PolicyError::RoleNotFound(role_id));
        }
        let assignment = RoleAssignment::new(role_id, session_id, tenant_id);
        self.role_assignments.push(assignment);
        Ok(())
    }

    /// Returns the number of registered roles.
    pub fn role_count(&self) -> usize {
        self.role_registry.len()
    }

    /// Returns the number of role assignments.
    pub fn assignment_count(&self) -> usize {
        self.role_assignments.len()
    }

    // -----------------------------------------------------------------------
    // Rule management
    // -----------------------------------------------------------------------

    /// Adds a policy rule to the engine.
    pub fn add_rule(
        &mut self,
        rule: crate::rule::PolicyRule,
    ) -> Result<(), PolicyError> {
        self.rule_set.add(rule)
    }

    /// Returns the number of policy rules.
    pub fn rule_count(&self) -> usize {
        self.rule_set.len()
    }

    // -----------------------------------------------------------------------
    // Safety veto management
    // -----------------------------------------------------------------------

    /// Registers a safety veto (immutable once added).
    pub fn register_veto(&mut self, veto: SafetyVeto) -> Result<(), PolicyError> {
        self.veto_registry.register(veto)
    }

    /// Returns the number of safety vetoes.
    pub fn veto_count(&self) -> usize {
        self.veto_registry.len()
    }

    // -----------------------------------------------------------------------
    // Criticality gate management
    // -----------------------------------------------------------------------

    /// Replaces the criticality gate with a new one built from the provided
    /// thresholds.
    ///
    /// E-12 FIX: The gate is now **immutable** after construction. To change
    /// thresholds, call this method with a fully-configured gate. This replaces
    /// the old `set_criticality_threshold()` which called a non-existent
    /// `CriticalityGate::set_threshold()` method — a compile error.
    ///
    /// The typical pattern is:
    /// ```ignore
    /// let gate = CriticalityGateBuilder::new()
    ///     .threshold(NodeCriticality::Low, CriticalityClearance::Critical)
    ///     .build();
    /// engine.replace_criticality_gate(gate);
    /// ```
    pub fn replace_criticality_gate(&mut self, gate: CriticalityGate) {
        self.criticality_gate = gate;
    }

    /// Returns the clearance required for a given criticality level.
    ///
    /// Useful for diagnostics and audit logging.
    pub fn required_clearance(&self, criticality: NodeCriticality) -> CriticalityClearance {
        self.criticality_gate.required_clearance(criticality)
    }

    // -----------------------------------------------------------------------
    // Audit log queries
    // -----------------------------------------------------------------------

    /// Returns the number of audit log entries.
    pub fn audit_count(&self) -> usize {
        self.audit_log.len()
    }

    /// Returns all audit log entries.
    pub fn audit_entries(&self) -> &[crate::audit::AuditEntry] {
        self.audit_log.entries()
    }

    /// Returns denial entries from the audit log.
    pub fn audit_denials(&self) -> Vec<&crate::audit::AuditEntry> {
        self.audit_log.denials()
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use zenic_proto::{NodeId, NodeCriticality, SessionId, TenantId};

    use crate::gate::{CriticalityGateBuilder, SafetyVeto};
    use crate::permission::{Action, Permission, Resource};
    use crate::role::{CriticalityClearance, Role, RoleId};
    use crate::rule::PolicyRule;

    use super::PolicyEngine;
    use super::super::types::PolicyContext;

    // -----------------------------------------------------------------------
    // Test helpers
    // -----------------------------------------------------------------------

    fn make_admin_role() -> Role {
        let mut role = Role::new("admin", "Administrator")
            .with_priority(crate::role::RolePriority::Admin)
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

    fn make_viewer_role() -> Role {
        let mut role = Role::new("viewer", "View-only")
            .with_priority(crate::role::RolePriority::Viewer)
            .with_clearance(CriticalityClearance::Low);
        role.add_permission(Permission::new(Action::Read, Resource::AllNodes));
        role
    }

    fn make_operator_role() -> Role {
        let mut role = Role::new("operator", "Standard operator")
            .with_priority(crate::role::RolePriority::Standard)
            .with_clearance(CriticalityClearance::High);
        role.add_permission(Permission::new(Action::Execute, Resource::AllNodes));
        role.add_permission(Permission::new(Action::Read, Resource::AllNodes));
        role.add_permission(Permission::new(Action::Write, Resource::AllNodes));
        role
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

    // -----------------------------------------------------------------------
    // PolicyEngine: default
    // -----------------------------------------------------------------------

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

    // -----------------------------------------------------------------------
    // PolicyEngine: criticality gate allows high clearance
    // -----------------------------------------------------------------------

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
}
