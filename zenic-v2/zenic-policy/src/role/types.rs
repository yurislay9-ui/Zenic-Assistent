//! Core RBAC type definitions: RoleId, RolePriority, CriticalityClearance,
//! and RoleAssignment.

use serde::{Deserialize, Serialize};
use std::fmt;
use std::str::FromStr;
use uuid::Uuid;

use zenic_proto::{NodeCriticality, SessionId, TenantId};

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
