//! Criticality gates and safety vetoes for the policy engine.
//!
//! [`CriticalityGate`] enforces that a session has sufficient role
//! clearance to interact with nodes of a given criticality level.
//!
//! [`SafetyVeto`] implements immutable deny rules that can never be
//! overridden by any role or policy rule. Safety vetoes are the
//! hard boundary that protects the system from unsafe operations.

use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use std::fmt;
use zenic_proto::{NodeCriticality, NodeId, SessionId};

use crate::errors::PolicyError;
use crate::permission::{Action, Permission, Resource};
use crate::role::{CriticalityClearance, Role};

// ---------------------------------------------------------------------------
// CriticalityGate
// ---------------------------------------------------------------------------

/// A gate that checks whether a session's roles provide sufficient
/// clearance for a node's criticality level.
///
/// The criticality gate is evaluated after RBAC permission checks.
/// Even if a session has the permission to execute a node, the gate
/// will deny access if the session's highest clearance level is
/// below the node's criticality.
///
/// The gate uses the highest clearance level among all assigned
/// roles for a session. A session with at least one role that
/// has `Critical` clearance can access any node.
///
/// **IMMUTABILITY INVARIANT**: Thresholds are set at construction time
/// and cannot be modified at runtime. This mirrors the same immutability
/// principle as [`SafetyVeto`] — security boundaries must never be
/// weakened after initialization. Use [`CriticalityGateBuilder`] to
/// configure custom thresholds before building.
pub struct CriticalityGate {
    /// Minimum clearance required for each criticality level.
    /// Immutable after construction — enforced by the absence of
    /// any public mutation method.
    thresholds: IndexMap<NodeCriticality, CriticalityClearance>,
}

impl CriticalityGate {
    /// Creates a criticality gate with default thresholds.
    ///
    /// Default thresholds:
    /// - `Low` criticality → `Low` clearance
    /// - `Medium` criticality → `Medium` clearance
    /// - `High` criticality → `High` clearance
    /// - `Critical` criticality → `Critical` clearance
    pub fn new() -> Self {
        let mut thresholds = IndexMap::new();
        thresholds.insert(NodeCriticality::Low, CriticalityClearance::Low);
        thresholds.insert(NodeCriticality::Medium, CriticalityClearance::Medium);
        thresholds.insert(NodeCriticality::High, CriticalityClearance::High);
        thresholds.insert(NodeCriticality::Critical, CriticalityClearance::Critical);
        Self { thresholds }
    }

    /// Checks whether the given roles provide sufficient clearance
    /// for the specified criticality level.
    ///
    /// Returns `Ok(())` if access is granted, or a `PolicyError`
    /// describing why the gate blocked access.
    pub fn check(
        &self,
        roles: &[&Role],
        criticality: NodeCriticality,
        session_id: SessionId,
        node_id: NodeId,
    ) -> Result<(), PolicyError> {
        // No roles means no clearance — deny immediately.
        if roles.is_empty() {
            return Err(PolicyError::CriticalityGateFailed {
                session_id,
                node_id,
                criticality,
            });
        }

        // Look up the required clearance from configured thresholds.
        let required_clearance = self
            .thresholds
            .get(&criticality)
            .copied()
            .unwrap_or(CriticalityClearance::Critical);

        // Find the highest clearance among the session's roles.
        let max_clearance = roles
            .iter()
            .map(|r| r.criticality_clearance)
            .max()
            .unwrap_or(CriticalityClearance::Low);

        // Check if the max clearance meets or exceeds the required clearance.
        if max_clearance >= required_clearance {
            Ok(())
        } else {
            Err(PolicyError::CriticalityGateFailed {
                session_id,
                node_id,
                criticality,
            })
        }
    }

    /// Returns the clearance required for a given criticality level.
    ///
    /// Useful for diagnostics and audit logging.
    pub fn required_clearance(&self, criticality: NodeCriticality) -> CriticalityClearance {
        self.thresholds
            .get(&criticality)
            .copied()
            .unwrap_or(CriticalityClearance::Critical)
    }
}

// ---------------------------------------------------------------------------
// CriticalityGateBuilder
// ---------------------------------------------------------------------------

/// Builder for constructing a [`CriticalityGate`] with custom thresholds.
///
/// Security boundaries (clearance thresholds) must be configured *before*
/// the gate is built. Once built, the gate is immutable. This prevents
/// runtime weakening of security boundaries — the same principle as
/// [`SafetyVeto`].
///
/// # Example
///
/// ```ignore
/// let gate = CriticalityGateBuilder::new()
///     .threshold(NodeCriticality::Low, CriticalityClearance::Critical)
///     .build();
/// ```
pub struct CriticalityGateBuilder {
    thresholds: IndexMap<NodeCriticality, CriticalityClearance>,
}

impl CriticalityGateBuilder {
    /// Creates a builder pre-populated with the default thresholds.
    pub fn new() -> Self {
        let mut thresholds = IndexMap::new();
        thresholds.insert(NodeCriticality::Low, CriticalityClearance::Low);
        thresholds.insert(NodeCriticality::Medium, CriticalityClearance::Medium);
        thresholds.insert(NodeCriticality::High, CriticalityClearance::High);
        thresholds.insert(NodeCriticality::Critical, CriticalityClearance::Critical);
        Self { thresholds }
    }

    /// Sets the clearance threshold for a specific criticality level.
    ///
    /// Can be called multiple times — last call wins for a given level.
    pub fn threshold(mut self, criticality: NodeCriticality, clearance: CriticalityClearance) -> Self {
        self.thresholds.insert(criticality, clearance);
        self
    }

    /// Builds the immutable [`CriticalityGate`].
    pub fn build(self) -> CriticalityGate {
        CriticalityGate {
            thresholds: self.thresholds,
        }
    }
}

impl Default for CriticalityGateBuilder {
    fn default() -> Self {
        Self::new()
    }
}

impl Default for CriticalityGate {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// SafetyVeto
// ---------------------------------------------------------------------------

/// A single immutable safety veto rule.
///
/// Safety vetoes are deny rules that can never be overridden by
/// any role, policy rule, or criticality gate. They represent
/// absolute safety boundaries for the system. Once registered,
/// a veto cannot be removed.
///
/// Examples of safety vetoes:
/// - "Never delete a Critical node"
/// - "Never modify the policy engine itself"
/// - "Never execute nodes in a suspended tenant"
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SafetyVeto {
    /// Human-readable name of this veto (must be unique).
    pub name: String,
    /// Description of why this veto exists.
    pub description: String,
    /// The action that this veto blocks.
    pub blocked_action: Action,
    /// The resource pattern this veto applies to.
    pub blocked_resource: Resource,
}

impl SafetyVeto {
    /// Creates a new safety veto.
    pub fn new(name: &str, description: &str, blocked_action: Action, blocked_resource: Resource) -> Self {
        Self {
            name: name.to_string(),
            description: description.to_string(),
            blocked_action,
            blocked_resource,
        }
    }

    /// Whether this veto blocks the given permission.
    ///
    /// A veto blocks a permission when:
    /// 1. The veto's blocked action matches the permission's action.
    /// 2. The veto's blocked resource implies the permission's resource.
    pub fn blocks(&self, permission: &Permission) -> bool {
        if self.blocked_action != permission.action {
            return false;
        }
        // Check if the blocked resource implies the permission's resource.
        let veto_perm = Permission::new(self.blocked_action, self.blocked_resource.clone());
        veto_perm.implies(permission)
    }

    /// Validates the veto for internal consistency.
    pub fn validate(&self) -> Result<(), PolicyError> {
        if self.name.is_empty() {
            return Err(PolicyError::Validation(
                "safety veto name must not be empty".to_string(),
            ));
        }
        Ok(())
    }
}

impl fmt::Display for SafetyVeto {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "veto:{}:{}", self.blocked_action, self.blocked_resource)
    }
}

// ---------------------------------------------------------------------------
// SafetyVetoRegistry
// ---------------------------------------------------------------------------

/// Registry of immutable safety vetoes.
///
/// Once a veto is registered, it cannot be removed. This ensures
/// that safety boundaries are never weakened at runtime.
pub struct SafetyVetoRegistry {
    vetoes: IndexMap<String, SafetyVeto>,
}

impl SafetyVetoRegistry {
    /// Creates an empty veto registry.
    pub fn new() -> Self {
        Self {
            vetoes: IndexMap::new(),
        }
    }

    /// Registers a safety veto.
    ///
    /// Returns an error if a veto with the same name already exists.
    /// Once registered, a veto cannot be removed.
    pub fn register(&mut self, veto: SafetyVeto) -> Result<(), PolicyError> {
        veto.validate()?;
        if self.vetoes.contains_key(&veto.name) {
            return Err(PolicyError::DuplicateVeto(veto.name.clone()));
        }
        self.vetoes.insert(veto.name.clone(), veto);
        Ok(())
    }

    /// Whether any registered veto blocks the given permission.
    pub fn is_blocked(&self, permission: &Permission) -> bool {
        self.vetoes.values().any(|v| v.blocks(permission))
    }

    /// Returns the veto that blocks the permission, if any.
    pub fn blocking_veto(&self, permission: &Permission) -> Option<&SafetyVeto> {
        self.vetoes.values().find(|v| v.blocks(permission))
    }

    /// Returns the number of registered vetoes.
    pub fn len(&self) -> usize {
        self.vetoes.len()
    }

    /// Whether the registry is empty.
    pub fn is_empty(&self) -> bool {
        self.vetoes.is_empty()
    }

    /// Returns an iterator over all registered vetoes.
    pub fn iter(&self) -> impl Iterator<Item = (&String, &SafetyVeto)> {
        self.vetoes.iter()
    }
}

impl Default for SafetyVetoRegistry {
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
        // Use the builder to configure custom thresholds at construction time.
        // Require Critical clearance even for Low criticality.
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
