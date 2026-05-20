//! Role registry: in-memory store for all defined roles.

use indexmap::IndexMap;

use crate::errors::PolicyError;
use zenic_proto::{SessionId, TenantId};

use super::permissions::Role;
use super::types::{RoleAssignment, RoleId};

// ---------------------------------------------------------------------------
// RoleRegistry
// ---------------------------------------------------------------------------

/// In-memory registry of all defined roles.
///
/// The registry provides fast lookup by role ID and ensures
/// that role IDs are unique. It is used by the policy engine
/// to resolve role assignments to permissions.
pub struct RoleRegistry {
    roles: IndexMap<RoleId, Role>,
}

impl RoleRegistry {
    /// Creates an empty role registry.
    pub fn new() -> Self {
        Self {
            roles: IndexMap::new(),
        }
    }

    /// Registers a role in the registry.
    ///
    /// Returns an error if a role with the same ID already exists.
    pub fn register(&mut self, role: Role) -> Result<(), PolicyError> {
        role.validate()?;
        if self.roles.contains_key(&role.id) {
            return Err(PolicyError::DuplicateRole(role.id));
        }
        self.roles.insert(role.id, role);
        Ok(())
    }

    /// Returns the role with the given ID, if it exists.
    pub fn get(&self, id: &RoleId) -> Option<&Role> {
        self.roles.get(id)
    }

    /// Whether a role with the given ID is registered.
    pub fn contains(&self, id: &RoleId) -> bool {
        self.roles.contains_key(id)
    }

    /// Returns the number of registered roles.
    pub fn len(&self) -> usize {
        self.roles.len()
    }

    /// Whether the registry is empty.
    pub fn is_empty(&self) -> bool {
        self.roles.is_empty()
    }

    /// Returns an iterator over all registered roles.
    pub fn iter(&self) -> impl Iterator<Item = (&RoleId, &Role)> {
        self.roles.iter()
    }

    /// Returns all roles assigned to a session within a tenant.
    pub fn roles_for_session(
        &self,
        assignments: &[RoleAssignment],
        session_id: &SessionId,
        tenant_id: &TenantId,
    ) -> Vec<&Role> {
        assignments
            .iter()
            .filter(|a| &a.session_id == session_id && &a.tenant_id == tenant_id)
            .filter_map(|a| self.roles.get(&a.role_id))
            .collect()
    }
}

impl Default for RoleRegistry {
    fn default() -> Self {
        Self::new()
    }
}
