//! Permission types for the policy engine.
//!
//! [`Action`] defines what operations can be performed.
//! [`Resource`] defines what entities can be operated on.
//! [`Permission`] pairs an action with a resource for access control.

use serde::{Deserialize, Serialize};
use std::fmt;
use zenic_proto::{NodeId, SubGraphId, SuperNodeId, WorkflowId};

// ---------------------------------------------------------------------------
// Action
// ---------------------------------------------------------------------------

/// Operations that a subject can perform on a resource.
///
/// Each action represents a distinct class of operation in the system.
/// The policy engine evaluates whether a given session is allowed to
/// perform a specific action on a specific resource.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Action {
    /// Execute a node, subgraph, or workflow.
    Execute,
    /// Read data or state.
    Read,
    /// Write or modify data and state.
    Write,
    /// Delete data, state, or entities.
    Delete,
    /// Administrative operations (full control).
    Admin,
    /// Manage roles and permissions.
    ManageRoles,
    /// View audit logs.
    ViewAudit,
    /// Cancel a running execution or workflow.
    Cancel,
}

impl Action {
    /// Returns all defined actions.
    pub fn all() -> &'static [Action] {
        &[
            Self::Execute,
            Self::Read,
            Self::Write,
            Self::Delete,
            Self::Admin,
            Self::ManageRoles,
            Self::ViewAudit,
            Self::Cancel,
        ]
    }
}

impl fmt::Display for Action {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Execute => write!(f, "execute"),
            Self::Read => write!(f, "read"),
            Self::Write => write!(f, "write"),
            Self::Delete => write!(f, "delete"),
            Self::Admin => write!(f, "admin"),
            Self::ManageRoles => write!(f, "manage_roles"),
            Self::ViewAudit => write!(f, "view_audit"),
            Self::Cancel => write!(f, "cancel"),
        }
    }
}

// ---------------------------------------------------------------------------
// Resource
// ---------------------------------------------------------------------------

/// Entities that can be acted upon by the policy engine.
///
/// Resources can be specific (identified by their ID) or general
/// (applying to all instances of a type). Specific resources take
/// precedence in policy evaluation.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Resource {
    /// A specific DAG node.
    Node(NodeId),
    /// A specific subgraph.
    SubGraph(SubGraphId),
    /// A specific supernode.
    SuperNode(SuperNodeId),
    /// A specific workflow.
    Workflow(WorkflowId),
    /// All nodes in the system.
    AllNodes,
    /// All subgraphs in the system.
    AllSubGraphs,
    /// All supernodes in the system.
    AllSuperNodes,
    /// All workflows in the system.
    AllWorkflows,
    /// The policy engine itself.
    PolicyEngine,
    /// The audit log.
    AuditLog,
    /// The role registry.
    RoleRegistry,
}

impl Resource {
    /// Whether this resource is a specific instance (has an ID).
    pub fn is_specific(&self) -> bool {
        matches!(
            self,
            Self::Node(_) | Self::SubGraph(_) | Self::SuperNode(_) | Self::Workflow(_)
        )
    }

    /// Whether this resource is a wildcard (applies to all instances of a type).
    pub fn is_wildcard(&self) -> bool {
        !self.is_specific()
    }

    /// Returns the resource type name for display purposes.
    pub fn type_name(&self) -> &'static str {
        match self {
            Self::Node(_) | Self::AllNodes => "node",
            Self::SubGraph(_) | Self::AllSubGraphs => "subgraph",
            Self::SuperNode(_) | Self::AllSuperNodes => "supernode",
            Self::Workflow(_) | Self::AllWorkflows => "workflow",
            Self::PolicyEngine => "policy_engine",
            Self::AuditLog => "audit_log",
            Self::RoleRegistry => "role_registry",
        }
    }
}

impl fmt::Display for Resource {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Node(id) => write!(f, "node:{}", id),
            Self::SubGraph(id) => write!(f, "subgraph:{}", id),
            Self::SuperNode(id) => write!(f, "supernode:{}", id),
            Self::Workflow(id) => write!(f, "workflow:{}", id),
            Self::AllNodes => write!(f, "all_nodes"),
            Self::AllSubGraphs => write!(f, "all_subgraphs"),
            Self::AllSuperNodes => write!(f, "all_supernodes"),
            Self::AllWorkflows => write!(f, "all_workflows"),
            Self::PolicyEngine => write!(f, "policy_engine"),
            Self::AuditLog => write!(f, "audit_log"),
            Self::RoleRegistry => write!(f, "role_registry"),
        }
    }
}

// ---------------------------------------------------------------------------
// Permission
// ---------------------------------------------------------------------------

/// A permission grants an action on a resource.
///
/// Permissions are assigned to roles. A session that has a role
/// inherits all of that role's permissions. The policy engine
/// checks whether a session has the required permission before
/// allowing an operation.
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Permission {
    /// The action this permission allows.
    pub action: Action,
    /// The resource this permission applies to.
    pub resource: Resource,
}

impl Permission {
    /// Creates a new permission for an action on a resource.
    pub fn new(action: Action, resource: Resource) -> Self {
        Self { action, resource }
    }

    /// Creates a wildcard permission: the action on all instances of a type.
    pub fn wildcard(action: Action, resource: Resource) -> Self {
        // The resource should already be a wildcard variant.
        Self { action, resource }
    }

    /// Whether this permission implies the given permission.
    ///
    /// A wildcard permission implies a specific permission of the same type.
    /// For example, `Execute AllNodes` implies `Execute Node(id)`.
    pub fn implies(&self, other: &Permission) -> bool {
        if self.action != other.action {
            return false;
        }
        self.resource_implies(&other.resource)
    }

    /// Checks whether this permission's resource implies the other resource.
    fn resource_implies(&self, other: &Resource) -> bool {
        if self.resource == *other {
            return true;
        }
        // Wildcard implies specific of the same type.
        matches!(
            (&self.resource, other),
            (Resource::AllNodes, Resource::Node(_))
                | (Resource::AllSubGraphs, Resource::SubGraph(_))
                | (Resource::AllSuperNodes, Resource::SuperNode(_))
                | (Resource::AllWorkflows, Resource::Workflow(_))
        )
    }

    /// Validates the permission for internal consistency.
    pub fn validate(&self) -> Result<(), String> {
        Ok(())
    }
}

impl fmt::Display for Permission {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}:{}", self.action, self.resource)
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn action_display() {
        assert_eq!(Action::Execute.to_string(), "execute");
        assert_eq!(Action::Admin.to_string(), "admin");
        assert_eq!(Action::ManageRoles.to_string(), "manage_roles");
        assert_eq!(Action::ViewAudit.to_string(), "view_audit");
        assert_eq!(Action::Cancel.to_string(), "cancel");
    }

    #[test]
    fn action_all_count() {
        assert_eq!(Action::all().len(), 8);
    }

    #[test]
    fn resource_specific_vs_wildcard() {
        let specific = Resource::Node(NodeId::new());
        assert!(specific.is_specific());
        assert!(!specific.is_wildcard());

        let wildcard = Resource::AllNodes;
        assert!(!wildcard.is_specific());
        assert!(wildcard.is_wildcard());
    }

    #[test]
    fn resource_type_name() {
        assert_eq!(Resource::AllNodes.type_name(), "node");
        assert_eq!(Resource::Node(NodeId::new()).type_name(), "node");
        assert_eq!(Resource::AllSubGraphs.type_name(), "subgraph");
        assert_eq!(Resource::PolicyEngine.type_name(), "policy_engine");
        assert_eq!(Resource::AuditLog.type_name(), "audit_log");
    }

    #[test]
    fn resource_display() {
        let id = NodeId::new();
        let specific = Resource::Node(id);
        assert!(specific.to_string().starts_with("node:"));

        let wildcard = Resource::AllNodes;
        assert_eq!(wildcard.to_string(), "all_nodes");
    }

    #[test]
    fn permission_new() {
        let perm = Permission::new(Action::Execute, Resource::AllNodes);
        assert_eq!(perm.action, Action::Execute);
        assert_eq!(perm.resource, Resource::AllNodes);
    }

    #[test]
    fn permission_implies_exact_match() {
        let id = NodeId::new();
        let perm1 = Permission::new(Action::Execute, Resource::Node(id));
        let perm2 = Permission::new(Action::Execute, Resource::Node(id));
        assert!(perm1.implies(&perm2));
    }

    #[test]
    fn permission_wildcard_implies_specific() {
        let wildcard = Permission::new(Action::Execute, Resource::AllNodes);
        let specific = Permission::new(Action::Execute, Resource::Node(NodeId::new()));
        assert!(wildcard.implies(&specific));
    }

    #[test]
    fn permission_specific_does_not_imply_wildcard() {
        let specific = Permission::new(Action::Execute, Resource::Node(NodeId::new()));
        let wildcard = Permission::new(Action::Execute, Resource::AllNodes);
        assert!(!specific.implies(&wildcard));
    }

    #[test]
    fn permission_different_action_does_not_imply() {
        let perm1 = Permission::new(Action::Execute, Resource::AllNodes);
        let perm2 = Permission::new(Action::Read, Resource::AllNodes);
        assert!(!perm1.implies(&perm2));
    }

    #[test]
    fn permission_cross_type_does_not_imply() {
        let perm1 = Permission::new(Action::Execute, Resource::AllNodes);
        let perm2 = Permission::new(Action::Execute, Resource::AllSubGraphs);
        assert!(!perm1.implies(&perm2));
    }

    #[test]
    fn permission_display() {
        let perm = Permission::new(Action::Execute, Resource::AllNodes);
        assert_eq!(perm.to_string(), "execute:all_nodes");
    }

    #[test]
    fn permission_validate() {
        let perm = Permission::new(Action::Read, Resource::PolicyEngine);
        assert!(perm.validate().is_ok());
    }
}
