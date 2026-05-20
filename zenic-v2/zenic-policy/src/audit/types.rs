//! Audit types: PolicyDecision, DenialReason, AuditEntry, AuditLog.

use serde::{Deserialize, Serialize};
use std::fmt;
use zenic_proto::{SessionId, TenantId};

use crate::permission::Permission;
use crate::role::RoleId;

// ---------------------------------------------------------------------------
// PolicyDecision
// ---------------------------------------------------------------------------

/// Outcome of a policy evaluation.
///
/// Each evaluation produces one of these decisions, which is then
/// recorded in the audit log.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum PolicyDecision {
    /// The action is allowed by the policy engine.
    Allowed,
    /// The action is denied by the policy engine.
    Denied,
}

impl fmt::Display for PolicyDecision {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Allowed => write!(f, "allowed"),
            Self::Denied => write!(f, "denied"),
        }
    }
}

// ---------------------------------------------------------------------------
// DenialReason
// ---------------------------------------------------------------------------

/// Why a policy evaluation resulted in a denial.
///
/// Denials can occur for several reasons, each with different
/// implications for the caller. This enum captures the specific
/// reason so that the audit log provides actionable information.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum DenialReason {
    /// No role assigned to the session grants the required permission.
    NoMatchingRole,
    /// A policy rule explicitly denied the action.
    RuleDenied(String),
    /// A safety veto blocked the action.
    SafetyVeto(String),
    /// The session's roles lack the criticality clearance.
    CriticalityGate,
    /// No policy rule matched (default-deny).
    DefaultDeny,
}

impl fmt::Display for DenialReason {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NoMatchingRole => write!(f, "no_matching_role"),
            Self::RuleDenied(name) => write!(f, "rule_denied:{}", name),
            Self::SafetyVeto(name) => write!(f, "safety_veto:{}", name),
            Self::CriticalityGate => write!(f, "criticality_gate"),
            Self::DefaultDeny => write!(f, "default_deny"),
        }
    }
}

// ---------------------------------------------------------------------------
// AuditEntry
// ---------------------------------------------------------------------------

/// A single audit entry recording a policy decision.
///
/// Audit entries are immutable once created. They capture the full
/// context of a policy evaluation, including the session, tenant,
/// requested permission, and the outcome.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AuditEntry {
    /// Monotonic timestamp when this decision was made (milliseconds).
    pub timestamp_ms: u64,
    /// The session that requested the action.
    pub session_id: SessionId,
    /// The tenant within which the action was requested.
    pub tenant_id: TenantId,
    /// The permission that was evaluated.
    pub permission: Permission,
    /// The decision outcome.
    pub decision: PolicyDecision,
    /// Why the decision was made (only set for denials).
    pub denial_reason: Option<DenialReason>,
    /// The roles that were considered during evaluation.
    pub role_ids: Vec<RoleId>,
}

impl AuditEntry {
    /// Creates a new audit entry for an allowed decision.
    pub fn allowed(
        timestamp_ms: u64,
        session_id: SessionId,
        tenant_id: TenantId,
        permission: Permission,
        role_ids: Vec<RoleId>,
    ) -> Self {
        Self {
            timestamp_ms,
            session_id,
            tenant_id,
            permission,
            decision: PolicyDecision::Allowed,
            denial_reason: None,
            role_ids,
        }
    }

    /// Creates a new audit entry for a denied decision.
    pub fn denied(
        timestamp_ms: u64,
        session_id: SessionId,
        tenant_id: TenantId,
        permission: Permission,
        reason: DenialReason,
        role_ids: Vec<RoleId>,
    ) -> Self {
        Self {
            timestamp_ms,
            session_id,
            tenant_id,
            permission,
            decision: PolicyDecision::Denied,
            denial_reason: Some(reason),
            role_ids,
        }
    }

    /// Whether this entry records a denial.
    pub fn is_denial(&self) -> bool {
        self.decision == PolicyDecision::Denied
    }

    /// Whether this entry records an allowance.
    pub fn is_allowance(&self) -> bool {
        self.decision == PolicyDecision::Allowed
    }
}

// ---------------------------------------------------------------------------
// AuditLog
// ---------------------------------------------------------------------------

/// In-memory audit log for policy decisions.
///
/// The audit log records every policy evaluation. For Phase 4,
/// the log is stored in memory. The `zenic-core` crate will
/// add disk persistence later.
pub struct AuditLog {
    entries: Vec<AuditEntry>,
    /// Monotonic clock for timestamps (milliseconds).
    clock_ms: u64,
}

impl AuditLog {
    /// Creates an empty audit log.
    pub fn new() -> Self {
        Self {
            entries: Vec::new(),
            clock_ms: 0,
        }
    }

    /// Records an allowed decision in the audit log.
    pub fn record_allowed(
        &mut self,
        session_id: SessionId,
        tenant_id: TenantId,
        permission: Permission,
        role_ids: Vec<RoleId>,
    ) {
        let entry = AuditEntry::allowed(
            self.next_timestamp(),
            session_id,
            tenant_id,
            permission,
            role_ids,
        );
        self.entries.push(entry);
    }

    /// Records a denied decision in the audit log.
    pub fn record_denied(
        &mut self,
        session_id: SessionId,
        tenant_id: TenantId,
        permission: Permission,
        reason: DenialReason,
        role_ids: Vec<RoleId>,
    ) {
        let entry = AuditEntry::denied(
            self.next_timestamp(),
            session_id,
            tenant_id,
            permission,
            reason,
            role_ids,
        );
        self.entries.push(entry);
    }

    /// Returns the number of entries in the audit log.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// Whether the audit log is empty.
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// Returns all entries in chronological order.
    pub fn entries(&self) -> &[AuditEntry] {
        &self.entries
    }

    /// Returns all denial entries.
    pub fn denials(&self) -> Vec<&AuditEntry> {
        self.entries.iter().filter(|e| e.is_denial()).collect()
    }

    /// Returns all allowance entries.
    pub fn allowances(&self) -> Vec<&AuditEntry> {
        self.entries.iter().filter(|e| e.is_allowance()).collect()
    }

    /// Returns entries for a specific session.
    pub fn entries_for_session(&self, session_id: &SessionId) -> Vec<&AuditEntry> {
        self.entries
            .iter()
            .filter(|e| &e.session_id == session_id)
            .collect()
    }

    /// Returns entries for a specific tenant.
    pub fn entries_for_tenant(&self, tenant_id: &TenantId) -> Vec<&AuditEntry> {
        self.entries
            .iter()
            .filter(|e| &e.tenant_id == tenant_id)
            .collect()
    }

    /// Returns the next monotonic timestamp and advances the clock.
    fn next_timestamp(&mut self) -> u64 {
        let ts = self.clock_ms;
        self.clock_ms += 1;
        ts
    }
}

impl Default for AuditLog {
    fn default() -> Self {
        Self::new()
    }
}
