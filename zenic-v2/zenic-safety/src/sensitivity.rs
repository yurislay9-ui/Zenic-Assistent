//! Data sensitivity levels for safety escalation.
//!
//! 4 levels: Low → Medium → High → Critical
//! Higher sensitivity escalates verdicts more aggressively.

use serde::{Deserialize, Serialize};
use std::fmt;

// ---------------------------------------------------------------------------
// DataSensitivity
// ---------------------------------------------------------------------------

/// Data sensitivity level for safety escalation.
///
/// When data sensitivity is high or critical, safety verdicts are
/// automatically escalated:
///
/// - Low: No escalation (base verdict stands)
/// - Medium: No escalation (base verdict stands)
/// - High: ALLOW → CONFIRM, CONFIRM → APPROVE
/// - Critical: ALLOW → CONFIRM, CONFIRM → APPROVE, APPROVE → DENY
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum DataSensitivity {
    Low,
    Medium,
    High,
    Critical,
}

impl DataSensitivity {
    /// All sensitivity levels in order.
    pub const ALL: [DataSensitivity; 4] = [
        DataSensitivity::Low,
        DataSensitivity::Medium,
        DataSensitivity::High,
        DataSensitivity::Critical,
    ];

    /// Returns the numeric level for comparison.
    pub fn level(&self) -> u8 {
        match self {
            Self::Low => 0,
            Self::Medium => 1,
            Self::High => 2,
            Self::Critical => 3,
        }
    }

    /// Whether this sensitivity level triggers verdict escalation.
    pub fn requires_escalation(&self) -> bool {
        matches!(self, Self::High | Self::Critical)
    }

    /// Escalate a verdict based on this sensitivity level.
    ///
    /// INVARIANT: Only escalates, never downgrades.
    pub fn escalate_verdict(&self, verdict: crate::verdict::SafetyVerdict) -> crate::verdict::SafetyVerdict {
        use crate::verdict::SafetyVerdict;
        match self {
            Self::Low | Self::Medium => verdict,
            Self::High => match verdict {
                SafetyVerdict::Allow => SafetyVerdict::Confirm,
                SafetyVerdict::Confirm => SafetyVerdict::Approve,
                other => other,
            },
            Self::Critical => match verdict {
                SafetyVerdict::Allow => SafetyVerdict::Confirm,
                SafetyVerdict::Confirm => SafetyVerdict::Approve,
                SafetyVerdict::Approve => SafetyVerdict::Deny,
                other => other,
            },
        }
    }

    /// Parse from string.
    pub fn from_str_lossy(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "low" => Some(Self::Low),
            "medium" | "med" => Some(Self::Medium),
            "high" => Some(Self::High),
            "critical" | "crit" => Some(Self::Critical),
            _ => None,
        }
    }
}

impl Ord for DataSensitivity {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.level().cmp(&other.level())
    }
}

impl PartialOrd for DataSensitivity {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl fmt::Display for DataSensitivity {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Low => write!(f, "low"),
            Self::Medium => write!(f, "medium"),
            Self::High => write!(f, "high"),
            Self::Critical => write!(f, "critical"),
        }
    }
}

impl Default for DataSensitivity {
    fn default() -> Self {
        Self::Low
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::verdict::SafetyVerdict;

    #[test]
    fn sensitivity_ordering() {
        assert!(DataSensitivity::Low < DataSensitivity::Medium);
        assert!(DataSensitivity::Medium < DataSensitivity::High);
        assert!(DataSensitivity::High < DataSensitivity::Critical);
    }

    #[test]
    fn sensitivity_no_escalation_low_medium() {
        assert!(!DataSensitivity::Low.requires_escalation());
        assert!(!DataSensitivity::Medium.requires_escalation());
    }

    #[test]
    fn sensitivity_escalation_high() {
        assert!(DataSensitivity::High.requires_escalation());
        assert_eq!(
            DataSensitivity::High.escalate_verdict(SafetyVerdict::Allow),
            SafetyVerdict::Confirm
        );
        assert_eq!(
            DataSensitivity::High.escalate_verdict(SafetyVerdict::Confirm),
            SafetyVerdict::Approve
        );
        // DENY stays DENY
        assert_eq!(
            DataSensitivity::High.escalate_verdict(SafetyVerdict::Deny),
            SafetyVerdict::Deny
        );
    }

    #[test]
    fn sensitivity_escalation_critical() {
        assert!(DataSensitivity::Critical.requires_escalation());
        assert_eq!(
            DataSensitivity::Critical.escalate_verdict(SafetyVerdict::Allow),
            SafetyVerdict::Confirm
        );
        assert_eq!(
            DataSensitivity::Critical.escalate_verdict(SafetyVerdict::Confirm),
            SafetyVerdict::Approve
        );
        assert_eq!(
            DataSensitivity::Critical.escalate_verdict(SafetyVerdict::Approve),
            SafetyVerdict::Deny
        );
    }

    #[test]
    fn sensitivity_from_str_lossy() {
        assert_eq!(DataSensitivity::from_str_lossy("high"), Some(DataSensitivity::High));
        assert_eq!(DataSensitivity::from_str_lossy("CRITICAL"), Some(DataSensitivity::Critical));
        assert_eq!(DataSensitivity::from_str_lossy("unknown"), None);
    }

    #[test]
    fn sensitivity_default_is_low() {
        assert_eq!(DataSensitivity::default(), DataSensitivity::Low);
    }
}
