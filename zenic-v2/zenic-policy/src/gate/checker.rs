//! Criticality gate checking and safety veto registry.

use indexmap::IndexMap;
use zenic_proto::{NodeCriticality, NodeId, SessionId};

use crate::errors::PolicyError;
use crate::permission::Permission;
use crate::role::{CriticalityClearance, Role};

use super::types::{CriticalityGate, SafetyVeto};

// ---------------------------------------------------------------------------
// CriticalityGate — check methods
// ---------------------------------------------------------------------------

impl CriticalityGate {
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
    use crate::permission::{Action, Permission, Resource};
    use crate::role::Role;
    use zenic_proto::{NodeId, NodeCriticality, SessionId};

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
