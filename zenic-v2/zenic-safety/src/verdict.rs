//! Safety verdict types with escalation semantics.
//!
//! Verdicts are ordered by severity:
//!   ALLOW < CONFIRM < APPROVE < DENY
//!
//! RATE_LIMITED is a special verdict that acts like DENY.
//!
//! INVARIANT: Domain rules can only escalate verdicts (move right),
//! never downgrade (move left).

use serde::{Deserialize, Serialize};
use std::fmt;

// ---------------------------------------------------------------------------
// SafetyVerdict
// ---------------------------------------------------------------------------

/// Safety gate verdict with escalation ordering.
///
/// The ordering is: ALLOW < CONFIRM < APPROVE < DENY
/// RATE_LIMITED is treated as equivalent to DENY for escalation purposes.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum SafetyVerdict {
    /// Action is allowed to proceed.
    Allow,
    /// Action requires user confirmation before proceeding.
    Confirm,
    /// Action requires higher-role approval before proceeding.
    Approve,
    /// Action is absolutely denied — no override possible.
    Deny,
    /// Too many actions in a time window — slow down.
    RateLimited,
}

impl SafetyVerdict {
    /// Returns the severity level for escalation comparison.
    ///
    /// ALLOW=0, CONFIRM=1, APPROVE=2, DENY=3, RATE_LIMITED=3
    pub fn severity(&self) -> u8 {
        match self {
            Self::Allow => 0,
            Self::Confirm => 1,
            Self::Approve => 2,
            Self::Deny => 3,
            Self::RateLimited => 3,
        }
    }

    /// Whether this verdict allows the action to proceed.
    ///
    /// Only ALLOW allows immediate execution.
    /// CONFIRM and APPROVE require additional steps.
    /// DENY and RATE_LIMITED block execution.
    pub fn can_proceed(&self) -> bool {
        matches!(self, Self::Allow | Self::Confirm | Self::Approve)
    }

    /// Escalate this verdict to a higher severity if the other verdict
    /// is more severe. Returns the escalated verdict.
    ///
    /// INVARIANT: Never downgrades.
    pub fn escalate(self, other: SafetyVerdict) -> SafetyVerdict {
        if other.severity() > self.severity() {
            other
        } else {
            self
        }
    }

    /// Whether this verdict represents a hard block.
    pub fn is_blocked(&self) -> bool {
        matches!(self, Self::Deny | Self::RateLimited)
    }
}

impl Ord for SafetyVerdict {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.severity().cmp(&other.severity())
    }
}

impl PartialOrd for SafetyVerdict {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl fmt::Display for SafetyVerdict {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Allow => write!(f, "ALLOW"),
            Self::Confirm => write!(f, "CONFIRM"),
            Self::Approve => write!(f, "APPROVE"),
            Self::Deny => write!(f, "DENY"),
            Self::RateLimited => write!(f, "RATE_LIMITED"),
        }
    }
}

impl Default for SafetyVerdict {
    fn default() -> Self {
        Self::Allow
    }
}

// ---------------------------------------------------------------------------
// ActionCategory
// ---------------------------------------------------------------------------

/// Classification of action risk level.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ActionCategory {
    /// Read-only, non-destructive.
    Safe,
    /// Write operations, single record.
    Moderate,
    /// Delete, drop, bulk operations.
    Destructive,
    /// Involves money, invoices, payments.
    Financial,
    /// System-level changes.
    System,
}

impl fmt::Display for ActionCategory {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Safe => write!(f, "safe"),
            Self::Moderate => write!(f, "moderate"),
            Self::Destructive => write!(f, "destructive"),
            Self::Financial => write!(f, "financial"),
            Self::System => write!(f, "system"),
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn verdict_severity_ordering() {
        assert!(SafetyVerdict::Allow < SafetyVerdict::Confirm);
        assert!(SafetyVerdict::Confirm < SafetyVerdict::Approve);
        assert!(SafetyVerdict::Approve < SafetyVerdict::Deny);
        assert_eq!(SafetyVerdict::RateLimited.severity(), SafetyVerdict::Deny.severity());
    }

    #[test]
    fn verdict_escalate_higher() {
        assert_eq!(
            SafetyVerdict::Allow.escalate(SafetyVerdict::Confirm),
            SafetyVerdict::Confirm
        );
        assert_eq!(
            SafetyVerdict::Confirm.escalate(SafetyVerdict::Deny),
            SafetyVerdict::Deny
        );
    }

    #[test]
    fn verdict_escalate_never_downgrades() {
        assert_eq!(
            SafetyVerdict::Deny.escalate(SafetyVerdict::Allow),
            SafetyVerdict::Deny
        );
        assert_eq!(
            SafetyVerdict::Approve.escalate(SafetyVerdict::Confirm),
            SafetyVerdict::Approve
        );
    }

    #[test]
    fn verdict_can_proceed() {
        assert!(SafetyVerdict::Allow.can_proceed());
        assert!(SafetyVerdict::Confirm.can_proceed());
        assert!(SafetyVerdict::Approve.can_proceed());
        assert!(!SafetyVerdict::Deny.can_proceed());
        assert!(!SafetyVerdict::RateLimited.can_proceed());
    }

    #[test]
    fn verdict_is_blocked() {
        assert!(!SafetyVerdict::Allow.is_blocked());
        assert!(SafetyVerdict::Deny.is_blocked());
        assert!(SafetyVerdict::RateLimited.is_blocked());
    }

    #[test]
    fn verdict_display() {
        assert_eq!(SafetyVerdict::Allow.to_string(), "ALLOW");
        assert_eq!(SafetyVerdict::Deny.to_string(), "DENY");
    }

    #[test]
    fn verdict_default_is_allow() {
        assert_eq!(SafetyVerdict::default(), SafetyVerdict::Allow);
    }
}
