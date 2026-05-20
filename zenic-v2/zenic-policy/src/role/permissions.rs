//! Role permissions: the [`Role`] struct and its permission-related methods.

use serde::{Deserialize, Serialize};
use zenic_proto::NodeCriticality;

use crate::errors::PolicyError;
use crate::permission::Permission;

use super::types::{CriticalityClearance, RoleId, RolePriority};

// ---------------------------------------------------------------------------
// Role
// ---------------------------------------------------------------------------

/// A named collection of permissions with a priority and criticality clearance.
///
/// Roles are the building blocks of RBAC. Each role defines what actions
/// are allowed on which resources, and at what priority level. Sessions
/// are assigned one or more roles, and the policy engine evaluates
/// permissions across all assigned roles.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Role {
    /// Unique identifier for this role.
    pub id: RoleId,
    /// Human-readable name (e.g., "admin", "viewer", "operator").
    pub name: String,
    /// Short description of what this role allows.
    pub description: String,
    /// Permissions granted by this role.
    pub permissions: Vec<Permission>,
    /// Priority level of this role.
    pub priority: RolePriority,
    /// Maximum criticality level this role can interact with.
    pub criticality_clearance: CriticalityClearance,
}

impl Role {
    /// Creates a new role with the given name and description.
    pub fn new(name: &str, description: &str) -> Self {
        Self {
            id: RoleId::new(),
            name: name.to_string(),
            description: description.to_string(),
            permissions: Vec::new(),
            priority: RolePriority::Standard,
            criticality_clearance: CriticalityClearance::Medium,
        }
    }

    /// Adds a permission to this role.
    pub fn add_permission(&mut self, permission: Permission) {
        if !self.permissions.contains(&permission) {
            self.permissions.push(permission);
        }
    }

    /// Sets the priority level of this role.
    pub fn with_priority(mut self, priority: RolePriority) -> Self {
        self.priority = priority;
        self
    }

    /// Sets the criticality clearance of this role.
    pub fn with_clearance(mut self, clearance: CriticalityClearance) -> Self {
        self.criticality_clearance = clearance;
        self
    }

    /// Whether this role grants a permission that implies the given permission.
    ///
    /// A role's wildcard permission (e.g., `Execute AllNodes`) implies
    /// a specific permission (e.g., `Execute Node(id)`).
    pub fn implies_permission(&self, permission: &Permission) -> bool {
        self.permissions.iter().any(|p| p.implies(permission))
    }

    /// Whether this role's clearance allows the given criticality level.
    pub fn allows_criticality(&self, criticality: NodeCriticality) -> bool {
        self.criticality_clearance.allows(criticality)
    }

    /// Validates the role for internal consistency.
    pub fn validate(&self) -> Result<(), PolicyError> {
        if self.name.is_empty() {
            return Err(PolicyError::Validation(
                "role name must not be empty".to_string(),
            ));
        }
        if self.name.contains(' ') {
            return Err(PolicyError::Validation(format!(
                "role name '{}' contains spaces (use snake_case)",
                self.name
            )));
        }
        for perm in &self.permissions {
            if let Err(e) = perm.validate() {
                return Err(PolicyError::Validation(format!(
                    "invalid permission in role '{}': {}",
                    self.name, e
                )));
            }
        }
        Ok(())
    }

    /// Returns the number of permissions in this role.
    pub fn permission_count(&self) -> usize {
        self.permissions.len()
    }
}
