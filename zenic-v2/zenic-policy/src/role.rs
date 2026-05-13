//! Role-Based Access Control (RBAC) types for the policy engine.
//!
//! A [`Role`] is a named collection of permissions. Sessions are assigned
//! roles, and the policy engine checks whether a session's roles grant
//! the required permission. [`RoleRegistry`] is the in-memory store for
//! all defined roles.

use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use std::fmt;
use std::str::FromStr;
use uuid::Uuid;

use zenic_proto::{NodeCriticality, SessionId, TenantId};

use crate::errors::PolicyError;
use crate::permission::Permission;

// ---------------------------------------------------------------------------
// RoleId
// ---------------------------------------------------------------------------

/// Unique identifier for a role.
///
/// Roles are identified by UUID. Each role has a unique ID that is
/// used to reference it in assignments and policy evaluation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct RoleId(Uuid);

impl RoleId {
    /// Generate a new random ID (v4).
    pub fn new() -> Self {
        Self(Uuid::new_v4())
    }

    /// Create from an existing [`Uuid`].
    pub const fn from_uuid(id: Uuid) -> Self {
        Self(id)
    }

    /// Return the inner [`Uuid`].
    pub const fn as_uuid(&self) -> &Uuid {
        &self.0
    }
}

impl fmt::Display for RoleId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl FromStr for RoleId {
    type Err = uuid::Error;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        Uuid::parse_str(s).map(Self)
    }
}

impl Default for RoleId {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// RolePriority
// ---------------------------------------------------------------------------

/// Priority level for a role.
///
/// Higher-priority roles take precedence during policy evaluation.
/// For example, a role with `Admin` priority can override a role
/// with `Standard` priority if both are assigned to the same session.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RolePriority {
    /// Lowest priority. Read-only or limited access roles.
    Viewer,
    /// Standard priority. Regular operational roles.
    Standard,
    /// Elevated priority. Roles that can modify system state.
    Elevated,
    /// Highest priority. Full administrative access.
    Admin,
}

impl RolePriority {
    /// Numeric weight for priority ordering (higher = more authoritative).
    pub fn weight(&self) -> u8 {
        match self {
            Self::Viewer => 1,
            Self::Standard => 2,
            Self::Elevated => 3,
            Self::Admin => 4,
        }
    }
}

impl fmt::Display for RolePriority {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Viewer => write!(f, "viewer"),
            Self::Standard => write!(f, "standard"),
            Self::Elevated => write!(f, "elevated"),
            Self::Admin => write!(f, "admin"),
        }
    }
}

impl Ord for RolePriority {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.weight().cmp(&other.weight())
    }
}

impl PartialOrd for RolePriority {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

// ---------------------------------------------------------------------------
// CriticalityClearance
// ---------------------------------------------------------------------------

/// The maximum node criticality a role is allowed to interact with.
///
/// This is used by the criticality gate to enforce that only
/// sufficiently privileged roles can execute, modify, or delete
/// nodes of a given criticality level.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum CriticalityClearance {
    /// Can interact with Low criticality nodes only.
    Low,
    /// Can interact with Low and Medium criticality nodes.
    Medium,
    /// Can interact with Low, Medium, and High criticality nodes.
    High,
    /// Can interact with nodes of any criticality, including Critical.
    Critical,
}

impl CriticalityClearance {
    /// Numeric weight for ordering (higher = more permissive).
    pub fn weight(&self) -> u8 {
        match self {
            Self::Low => 1,
            Self::Medium => 2,
            Self::High => 3,
            Self::Critical => 4,
        }
    }

    /// Whether this clearance level allows interaction with the given criticality.
    pub fn allows(&self, criticality: NodeCriticality) -> bool {
        match (self, criticality) {
            (Self::Critical, _) => true,
            (Self::High, NodeCriticality::Critical) => false,
            (Self::High, _) => true,
            (Self::Medium, NodeCriticality::Critical | NodeCriticality::High) => false,
            (Self::Medium, _) => true,
            (Self::Low, NodeCriticality::Low) => true,
            (Self::Low, _) => false,
        }
    }

    /// Returns the corresponding NodeCriticality level for this clearance.
    pub fn as_criticality(&self) -> NodeCriticality {
        match self {
            Self::Low => NodeCriticality::Low,
            Self::Medium => NodeCriticality::Medium,
            Self::High => NodeCriticality::High,
            Self::Critical => NodeCriticality::Critical,
        }
    }
}

impl fmt::Display for CriticalityClearance {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Low => write!(f, "low"),
            Self::Medium => write!(f, "medium"),
            Self::High => write!(f, "high"),
            Self::Critical => write!(f, "critical"),
        }
    }
}

impl Ord for CriticalityClearance {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.weight().cmp(&other.weight())
    }
}

impl PartialOrd for CriticalityClearance {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

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

// ---------------------------------------------------------------------------
// RoleAssignment
// ---------------------------------------------------------------------------

/// Associates a role with a session within a tenant.
///
/// Role assignments are the link between sessions and roles. A session
/// may have multiple roles assigned, and the policy engine evaluates
/// permissions across all of them.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RoleAssignment {
    /// The role being assigned.
    pub role_id: RoleId,
    /// The session receiving the role.
    pub session_id: SessionId,
    /// The tenant within which this assignment is valid.
    pub tenant_id: TenantId,
}

impl RoleAssignment {
    /// Creates a new role assignment.
    pub fn new(role_id: RoleId, session_id: SessionId, tenant_id: TenantId) -> Self {
        Self {
            role_id,
            session_id,
            tenant_id,
        }
    }
}

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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::permission::{Action, Resource};
    use zenic_proto::NodeId;

    #[test]
    fn role_id_display_roundtrip() {
        let id = RoleId::new();
        let s = id.to_string();
        let parsed: RoleId = s.parse().expect("valid parse");
        assert_eq!(id, parsed);
    }

    #[test]
    fn role_id_default_generates_unique() {
        let a = RoleId::default();
        let b = RoleId::default();
        assert_ne!(a, b);
    }

    #[test]
    fn role_id_invalid_parse() {
        let result = RoleId::from_str("not-a-uuid");
        assert!(result.is_err());
    }

    #[test]
    fn role_priority_ordering() {
        assert!(RolePriority::Admin > RolePriority::Elevated);
        assert!(RolePriority::Elevated > RolePriority::Standard);
        assert!(RolePriority::Standard > RolePriority::Viewer);
    }

    #[test]
    fn role_priority_display() {
        assert_eq!(RolePriority::Admin.to_string(), "admin");
        assert_eq!(RolePriority::Viewer.to_string(), "viewer");
    }

    #[test]
    fn criticality_clearance_allows() {
        assert!(CriticalityClearance::Critical.allows(NodeCriticality::Critical));
        assert!(CriticalityClearance::Critical.allows(NodeCriticality::Low));
        assert!(CriticalityClearance::High.allows(NodeCriticality::High));
        assert!(!CriticalityClearance::High.allows(NodeCriticality::Critical));
        assert!(CriticalityClearance::Medium.allows(NodeCriticality::Medium));
        assert!(!CriticalityClearance::Medium.allows(NodeCriticality::High));
        assert!(CriticalityClearance::Low.allows(NodeCriticality::Low));
        assert!(!CriticalityClearance::Low.allows(NodeCriticality::Medium));
    }

    #[test]
    fn criticality_clearance_as_criticality() {
        assert_eq!(CriticalityClearance::Critical.as_criticality(), NodeCriticality::Critical);
        assert_eq!(CriticalityClearance::High.as_criticality(), NodeCriticality::High);
    }

    #[test]
    fn role_new() {
        let role = Role::new("operator", "Standard operator role");
        assert_eq!(role.name, "operator");
        assert!(role.permissions.is_empty());
        assert_eq!(role.priority, RolePriority::Standard);
        assert_eq!(role.criticality_clearance, CriticalityClearance::Medium);
    }

    #[test]
    fn role_add_permission() {
        let mut role = Role::new("admin", "Administrator");
        role.add_permission(Permission::new(Action::Admin, Resource::AllNodes));
        assert_eq!(role.permission_count(), 1);
    }

    #[test]
    fn role_add_duplicate_permission_ignored() {
        let mut role = Role::new("admin", "Administrator");
        let perm = Permission::new(Action::Admin, Resource::AllNodes);
        role.add_permission(perm.clone());
        role.add_permission(perm);
        assert_eq!(role.permission_count(), 1);
    }

    #[test]
    fn role_with_priority_and_clearance() {
        let role = Role::new("super_admin", "Super administrator")
            .with_priority(RolePriority::Admin)
            .with_clearance(CriticalityClearance::Critical);
        assert_eq!(role.priority, RolePriority::Admin);
        assert_eq!(role.criticality_clearance, CriticalityClearance::Critical);
    }

    #[test]
    fn role_implies_permission_wildcard() {
        let mut role = Role::new("executor", "Can execute any node");
        role.add_permission(Permission::new(Action::Execute, Resource::AllNodes));
        let specific = Permission::new(Action::Execute, Resource::Node(NodeId::new()));
        assert!(role.implies_permission(&specific));
    }

    #[test]
    fn role_does_not_imply_different_action() {
        let mut role = Role::new("reader", "Can read any node");
        role.add_permission(Permission::new(Action::Read, Resource::AllNodes));
        let execute_perm = Permission::new(Action::Execute, Resource::Node(NodeId::new()));
        assert!(!role.implies_permission(&execute_perm));
    }

    #[test]
    fn role_allows_criticality() {
        let role = Role::new("high_role", "High clearance")
            .with_clearance(CriticalityClearance::High);
        assert!(role.allows_criticality(NodeCriticality::High));
        assert!(!role.allows_criticality(NodeCriticality::Critical));
    }

    #[test]
    fn role_validate_valid() {
        let role = Role::new("valid_role", "A valid role");
        assert!(role.validate().is_ok());
    }

    #[test]
    fn role_validate_empty_name() {
        let role = Role {
            id: RoleId::new(),
            name: String::new(),
            description: "No name".to_string(),
            permissions: Vec::new(),
            priority: RolePriority::Standard,
            criticality_clearance: CriticalityClearance::Medium,
        };
        assert!(role.validate().is_err());
    }

    #[test]
    fn role_validate_space_in_name() {
        let role = Role {
            id: RoleId::new(),
            name: "has space".to_string(),
            description: "Bad name".to_string(),
            permissions: Vec::new(),
            priority: RolePriority::Standard,
            criticality_clearance: CriticalityClearance::Medium,
        };
        assert!(role.validate().is_err());
    }

    #[test]
    fn role_assignment_new() {
        let assignment = RoleAssignment::new(RoleId::new(), SessionId::new(), TenantId::new());
        assert_eq!(assignment.role_id, assignment.role_id);
    }

    #[test]
    fn role_registry_register_and_get() {
        let mut registry = RoleRegistry::new();
        let role = Role::new("viewer", "View-only role");
        let id = role.id;
        registry.register(role).expect("register");
        assert_eq!(registry.len(), 1);
        assert!(registry.contains(&id));
        assert!(registry.get(&id).is_some());
    }

    #[test]
    fn role_registry_duplicate_fails() {
        let mut registry = RoleRegistry::new();
        let role = Role::new("viewer", "View-only role");
        let id = role.id;
        registry.register(role).expect("register");
        let duplicate = Role {
            id,
            name: "duplicate".to_string(),
            description: "Duplicate ID".to_string(),
            permissions: Vec::new(),
            priority: RolePriority::Standard,
            criticality_clearance: CriticalityClearance::Medium,
        };
        let result = registry.register(duplicate);
        assert!(result.is_err());
    }

    #[test]
    fn role_registry_default_is_new() {
        let registry = RoleRegistry::default();
        assert!(registry.is_empty());
    }

    #[test]
    fn role_registry_roles_for_session() {
        let mut registry = RoleRegistry::new();
        let role1 = Role::new("viewer", "View-only");
        let role2 = Role::new("editor", "Edit access");
        let rid1 = role1.id;
        let rid2 = role2.id;
        registry.register(role1).expect("register");
        registry.register(role2).expect("register");

        let sid = SessionId::new();
        let tid = TenantId::new();
        let assignments = vec![
            RoleAssignment::new(rid1, sid, tid),
            RoleAssignment::new(rid2, sid, tid),
        ];

        let roles = registry.roles_for_session(&assignments, &sid, &tid);
        assert_eq!(roles.len(), 2);
    }

    #[test]
    fn role_registry_roles_for_session_different_tenant() {
        let mut registry = RoleRegistry::new();
        let role = Role::new("viewer", "View-only");
        let rid = role.id;
        registry.register(role).expect("register");

        let sid = SessionId::new();
        let tid1 = TenantId::new();
        let tid2 = TenantId::new();
        let assignments = vec![RoleAssignment::new(rid, sid, tid1)];

        let roles = registry.roles_for_session(&assignments, &sid, &tid2);
        assert!(roles.is_empty());
    }
}
