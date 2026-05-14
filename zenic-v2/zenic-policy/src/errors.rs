//! Error types for the policy layer.

use thiserror::Error;
use zenic_proto::{NodeId, PolicyId, SessionId, TenantId};

use crate::permission::Permission;
use crate::role::RoleId;

/// Errors that can occur during policy evaluation and enforcement.
#[derive(Debug, Error)]
pub enum PolicyError {
    /// A permission was denied by the policy engine.
    #[error("permission denied: session {session_id} cannot {permission} in tenant {tenant_id}")]
    PermissionDenied {
        session_id: SessionId,
        permission: Permission,
        tenant_id: TenantId,
    },

    /// A safety veto blocked the action.
    #[error("safety veto: {rule_name} blocked action on {resource}")]
    SafetyVetoTriggered {
        rule_name: String,
        resource: String,
    },

    /// A criticality gate blocked the action.
    #[error("criticality gate: session {session_id} lacks clearance for {criticality:?} node {node_id}")]
    CriticalityGateFailed {
        session_id: SessionId,
        node_id: NodeId,
        criticality: zenic_proto::NodeCriticality,
    },

    /// A role was not found in the registry.
    #[error("role not found: {0}")]
    RoleNotFound(RoleId),

    /// A policy rule was not found.
    #[error("policy rule not found: {0}")]
    RuleNotFound(PolicyId),

    /// A duplicate role was registered.
    #[error("duplicate role: {0}")]
    DuplicateRole(RoleId),

    /// A duplicate policy rule was registered.
    #[error("duplicate policy rule: {0}")]
    DuplicateRule(PolicyId),

    /// A duplicate safety veto was registered.
    #[error("duplicate safety veto: {0}")]
    DuplicateVeto(String),

    /// Validation of a policy rule failed.
    #[error("policy validation error: {0}")]
    Validation(String),

    /// The role has no permissions assigned.
    #[error("role {role_id} has no permissions")]
    EmptyRolePermissions { role_id: RoleId },

    /// A general policy error.
    #[error("policy error: {0}")]
    General(String),
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::permission::{Action, Resource};

    #[test]
    fn permission_denied_display() {
        let err = PolicyError::PermissionDenied {
            session_id: SessionId::new(),
            permission: Permission::new(Action::Execute, Resource::Node(NodeId::new())),
            tenant_id: TenantId::new(),
        };
        let msg = err.to_string();
        assert!(msg.contains("permission denied"));
    }

    #[test]
    fn safety_veto_display() {
        let err = PolicyError::SafetyVetoTriggered {
            rule_name: "no_delete_critical".to_string(),
            resource: "node:abc".to_string(),
        };
        let msg = err.to_string();
        assert!(msg.contains("safety veto"));
        assert!(msg.contains("no_delete_critical"));
    }

    #[test]
    fn criticality_gate_display() {
        let err = PolicyError::CriticalityGateFailed {
            session_id: SessionId::new(),
            node_id: NodeId::new(),
            criticality: zenic_proto::NodeCriticality::Critical,
        };
        let msg = err.to_string();
        assert!(msg.contains("criticality gate"));
    }

    #[test]
    fn role_not_found_display() {
        let id = RoleId::new();
        let err = PolicyError::RoleNotFound(id);
        assert!(err.to_string().contains("role not found"));
    }

    #[test]
    fn rule_not_found_display() {
        let id = PolicyId::new();
        let err = PolicyError::RuleNotFound(id);
        assert!(err.to_string().contains("policy rule not found"));
    }

    #[test]
    fn duplicate_role_display() {
        let id = RoleId::new();
        let err = PolicyError::DuplicateRole(id);
        assert!(err.to_string().contains("duplicate role"));
    }

    #[test]
    fn validation_error_display() {
        let err = PolicyError::Validation("empty rule name".to_string());
        assert!(err.to_string().contains("empty rule name"));
    }

    #[test]
    fn general_error_display() {
        let err = PolicyError::General("something went wrong".to_string());
        assert!(err.to_string().contains("something went wrong"));
    }
}
