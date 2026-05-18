//! Core types for the criticality gate and safety veto modules.

use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use std::fmt;
use zenic_proto::NodeCriticality;

use crate::errors::PolicyError;
use crate::permission::{Action, Permission, Resource};
use crate::role::CriticalityClearance;

// ---------------------------------------------------------------------------
// CriticalityGate (struct only)
// ---------------------------------------------------------------------------

/// A gate that checks whether a session's roles provide sufficient
/// clearance for a node's criticality level.
///
/// The criticality gate is evaluated after RBAC permission checks.
/// Even if a session has the permission to execute a node, the gate
/// will deny access if the session's highest clearance level is
/// below the node's criticality.
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
    pub(crate) thresholds: IndexMap<NodeCriticality, CriticalityClearance>,
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
