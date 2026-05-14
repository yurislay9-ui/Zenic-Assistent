//! Policy engine: the main evaluation engine for access control.
//!
//! The [`PolicyEngine`] is the central component of the policy layer.
//! It coordinates RBAC permission checks, policy rule evaluation,
//! safety veto enforcement, and criticality gate checks. Every
//! access decision passes through the engine and is recorded in
//! the audit log.
//!
//! Evaluation order (first failure stops):
//! 1. Safety veto check — immutable deny rules.
//! 2. RBAC permission check — does any role grant the permission?
//! 3. Policy rule evaluation — explicit allow/deny rules.
//! 4. Criticality gate — sufficient clearance for the node?
//! 5. Default deny — if nothing matched, deny.

use zenic_proto::{BusinessDomain, NodeCriticality, NodeId, SessionId, TenantId};

use crate::audit::{AuditLog, DenialReason, PolicyDecision};
use crate::errors::PolicyError;
use crate::gate::{CriticalityGate, CriticalityGateBuilder, SafetyVeto, SafetyVetoRegistry};
use crate::permission::Permission;
use crate::role::{Role, RoleAssignment, RoleId, RoleRegistry};
use crate::rule::{RuleEffect, RuleSet};

// ---------------------------------------------------------------------------
// PolicyContext
// ---------------------------------------------------------------------------

/// Context for a single policy evaluation request.
///
/// Contains all the information needed to make an access decision:
/// who is requesting, what they want to do, and optional context
/// about the target (domain, criticality).
pub struct PolicyContext {
    /// The session making the request.
    pub session_id: SessionId,
    /// The tenant within which the request is made.
    pub tenant_id: TenantId,
    /// The permission being requested.
    pub permission: Permission,
    /// Optional business domain of the target resource.
    pub domain: Option<BusinessDomain>,
    /// Optional criticality of the target node (for gate checks).
    pub criticality: Option<NodeCriticality>,
    /// Optional node ID for the target (for gate checks).
    pub node_id: Option<NodeId>,
}

impl PolicyContext {
    /// Creates a basic policy context with just session, tenant, and permission.
    pub fn new(
        session_id: SessionId,
        tenant_id: TenantId,
        permission: Permission,
    ) -> Self {
        Self {
            session_id,
            tenant_id,
            permission,
            domain: None,
            criticality: None,
            node_id: None,
        }
    }

    /// Adds domain context to the policy request.
    pub fn with_domain(mut self, domain: BusinessDomain) -> Self {
        self.domain = Some(domain);
        self
    }

    /// Adds criticality context for gate checks.
    pub fn with_criticality(mut self, criticality: NodeCriticality, node_id: NodeId) -> Self {
        self.criticality = Some(criticality);
        self.node_id = Some(node_id);
        self
    }
}

// ---------------------------------------------------------------------------
// PolicyEngine
// ---------------------------------------------------------------------------

/// The main policy evaluation engine.
///
/// The engine coordinates all policy sub-systems:
/// - [`RoleRegistry`] — RBAC role definitions and lookup.
/// - [`RuleSet`] — explicit allow/deny policy rules.
/// - [`SafetyVetoRegistry`] — immutable deny rules.
/// - [`CriticalityGate`] — criticality clearance enforcement.
/// - [`AuditLog`] — decision audit trail.
///
/// Evaluation follows a strict order where the first failure
/// stops the evaluation and returns a denial. This ensures
/// that safety vetoes are always checked first, followed by
/// RBAC, rules, and criticality gates.
pub struct PolicyEngine {
    /// RBAC role registry.
    role_registry: RoleRegistry,
    /// Role assignments (session → role mappings).
    role_assignments: Vec<RoleAssignment>,
    /// Policy rule set.
    rule_set: RuleSet,
    /// Safety veto registry (immutable once registered).
    veto_registry: SafetyVetoRegistry,
    /// Criticality gate.
    criticality_gate: CriticalityGate,
    /// Audit log for all decisions.
    audit_log: AuditLog,
}

impl PolicyEngine {
    /// Creates a new policy engine with empty registries.
    pub fn new() -> Self {
        Self {
            role_registry: RoleRegistry::new(),
            role_assignments: Vec::new(),
            rule_set: RuleSet::new(),
            veto_registry: SafetyVetoRegistry::new(),
            criticality_gate: CriticalityGate::new(),
            audit_log: AuditLog::new(),
        }
    }

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
    pub fn required_clearance(&self, criticality: NodeCriticality) -> crate::role::CriticalityClearance {
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

    // -----------------------------------------------------------------------
    // Evaluation
    // -----------------------------------------------------------------------

    /// Evaluates a policy request and returns the decision.
    ///
    /// Evaluation order:
    /// 1. Safety veto check — if any veto blocks the permission, deny.
    /// 2. RBAC check — if no role grants the permission, deny.
    /// 3. Rule evaluation — if an explicit deny rule matches, deny.
    ///    If an explicit allow rule matches, allow.
    /// 4. Criticality gate — if the target has a criticality level
    ///    and the session's roles lack clearance, deny.
    /// 5. Default deny — if nothing matched, deny.
    pub fn evaluate(&mut self, ctx: &PolicyContext) -> Result<PolicyDecision, PolicyError> {
        let roles = self.role_registry.roles_for_session(
            &self.role_assignments,
            &ctx.session_id,
            &ctx.tenant_id,
        );
        let role_ids: Vec<RoleId> = roles.iter().map(|r| r.id).collect();

        // Step 1: Safety veto check.
        if let Some(veto) = self.veto_registry.blocking_veto(&ctx.permission) {
            self.audit_log.record_denied(
                ctx.session_id,
                ctx.tenant_id,
                ctx.permission.clone(),
                DenialReason::SafetyVeto(veto.name.clone()),
                role_ids,
            );
            return Err(PolicyError::SafetyVetoTriggered {
                rule_name: veto.name.clone(),
                resource: ctx.permission.resource.to_string(),
            });
        }

        // Step 2: RBAC permission check.
        let has_rbac_permission = roles.iter().any(|r| r.implies_permission(&ctx.permission));
        if !has_rbac_permission {
            self.audit_log.record_denied(
                ctx.session_id,
                ctx.tenant_id,
                ctx.permission.clone(),
                DenialReason::NoMatchingRole,
                role_ids,
            );
            return Err(PolicyError::PermissionDenied {
                session_id: ctx.session_id,
                permission: ctx.permission.clone(),
                tenant_id: ctx.tenant_id,
            });
        }

        // Step 3: Policy rule evaluation.
        let rule_effect = self.rule_set.evaluate(&ctx.permission, ctx.domain);
        match rule_effect {
            Some(RuleEffect::Deny) => {
                self.audit_log.record_denied(
                    ctx.session_id,
                    ctx.tenant_id,
                    ctx.permission.clone(),
                    DenialReason::RuleDenied("explicit_deny".to_string()),
                    role_ids,
                );
                return Err(PolicyError::PermissionDenied {
                    session_id: ctx.session_id,
                    permission: ctx.permission.clone(),
                    tenant_id: ctx.tenant_id,
                });
            }
            Some(RuleEffect::Allow) => {
                // Rule explicitly allows. Continue to criticality gate.
            }
            None => {
                // No rule matched. Default deny.
                self.audit_log.record_denied(
                    ctx.session_id,
                    ctx.tenant_id,
                    ctx.permission.clone(),
                    DenialReason::DefaultDeny,
                    role_ids,
                );
                return Err(PolicyError::PermissionDenied {
                    session_id: ctx.session_id,
                    permission: ctx.permission.clone(),
                    tenant_id: ctx.tenant_id,
                });
            }
        }

        // Step 4: Criticality gate check.
        if let (Some(criticality), Some(node_id)) = (ctx.criticality, ctx.node_id) {
            if let Err(e) = self.criticality_gate.check(
                &roles,
                criticality,
                ctx.session_id,
                node_id,
            ) {
                self.audit_log.record_denied(
                    ctx.session_id,
                    ctx.tenant_id,
                    ctx.permission.clone(),
                    DenialReason::CriticalityGate,
                    role_ids,
                );
                return Err(e);
            }
        }

        // Step 5: All checks passed. Allow.
        self.audit_log.record_allowed(
            ctx.session_id,
            ctx.tenant_id,
            ctx.permission.clone(),
            role_ids,
        );
        Ok(PolicyDecision::Allowed)
    }

    /// Convenience method: checks if a session is allowed to perform
    /// an action, returning a boolean without error details.
    pub fn is_allowed(&mut self, ctx: &PolicyContext) -> bool {
        self.evaluate(ctx).is_ok()
    }
}

impl Default for PolicyEngine {
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
    use crate::role::CriticalityClearance;
    use crate::rule::PolicyRule;

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

        // Add an allow rule.
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

        // Register a safety veto that blocks deletion.
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
}
