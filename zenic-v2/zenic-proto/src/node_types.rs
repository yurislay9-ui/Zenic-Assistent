//! Node classification types for the fractal DAG.
//!
//! These types describe HOW a node behaves, WHEN it is loaded,
//! and HOW CRITICAL it is for the system.

use serde::{Deserialize, Serialize};
use std::fmt;

// ---------------------------------------------------------------------------
// NodeCategory
// ---------------------------------------------------------------------------

/// Functional category of a DAG node.
///
/// Determines what kind of operation a node performs within the business
/// assistance pipeline. This is orthogonal to [`BusinessDomain`](super::domain::BusinessDomain):
/// the domain determines *which* business context, while the category
/// determines *what* the node does.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum NodeCategory {
    /// Core pipeline orchestration (entry, routing, exit).
    Orchestrator,
    /// Ingest data from external sources (APIs, files, databases).
    DataIngestion,
    /// Transform, clean, or normalize data.
    DataTransform,
    /// Validate data against schema or business rules.
    DataValidation,
    /// Make a deterministic business decision (branching logic).
    Decision,
    /// Evaluate a condition or score (e.g., risk score, priority).
    Evaluation,
    /// Route execution to one of several paths based on context.
    Routing,
    /// Connect to external APIs or services.
    ApiConnector,
    /// Send notifications (email, SMS, push, webhook).
    Notification,
    /// Manage persistent state (CRUD on business entities).
    StateManagement,
    /// Audit trail and compliance logging.
    Audit,
    /// Regulatory compliance check.
    Compliance,
    /// Generate analytics, metrics, or reports.
    Analytics,
    /// Render or format output (reports, dashboards, PDFs).
    Reporting,
    /// Manage user/business identity and access.
    Identity,
    /// Scheduling and time-based triggers.
    Scheduler,
    /// Verdict arbitration (LLM YES/NO interface).
    Verdict,
}

impl NodeCategory {
    /// Returns all defined categories.
    pub fn all() -> &'static [NodeCategory] {
        &[
            Self::Orchestrator,
            Self::DataIngestion,
            Self::DataTransform,
            Self::DataValidation,
            Self::Decision,
            Self::Evaluation,
            Self::Routing,
            Self::ApiConnector,
            Self::Notification,
            Self::StateManagement,
            Self::Audit,
            Self::Compliance,
            Self::Analytics,
            Self::Reporting,
            Self::Identity,
            Self::Scheduler,
            Self::Verdict,
        ]
    }
}

impl fmt::Display for NodeCategory {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Orchestrator => write!(f, "orchestrator"),
            Self::DataIngestion => write!(f, "data_ingestion"),
            Self::DataTransform => write!(f, "data_transform"),
            Self::DataValidation => write!(f, "data_validation"),
            Self::Decision => write!(f, "decision"),
            Self::Evaluation => write!(f, "evaluation"),
            Self::Routing => write!(f, "routing"),
            Self::ApiConnector => write!(f, "api_connector"),
            Self::Notification => write!(f, "notification"),
            Self::StateManagement => write!(f, "state_management"),
            Self::Audit => write!(f, "audit"),
            Self::Compliance => write!(f, "compliance"),
            Self::Analytics => write!(f, "analytics"),
            Self::Reporting => write!(f, "reporting"),
            Self::Identity => write!(f, "identity"),
            Self::Scheduler => write!(f, "scheduler"),
            Self::Verdict => write!(f, "verdict"),
        }
    }
}

// ---------------------------------------------------------------------------
// NodeCriticality
// ---------------------------------------------------------------------------

/// How critical a node is for the system to function.
///
/// Used by the Policy Engine to determine failure handling and by the
/// Runtime to decide whether a node must always be in RAM.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum NodeCriticality {
    /// System cannot function without this node.
    Critical,
    /// A major feature depends on this node.
    High,
    /// Important but not blocking other nodes.
    Medium,
    /// Optional enhancement, nice-to-have.
    Low,
}

impl NodeCriticality {
    /// Numeric weight for priority ordering (higher = more critical).
    pub fn weight(&self) -> u8 {
        match self {
            Self::Critical => 4,
            Self::High => 3,
            Self::Medium => 2,
            Self::Low => 1,
        }
    }
}

impl fmt::Display for NodeCriticality {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Critical => write!(f, "critical"),
            Self::High => write!(f, "high"),
            Self::Medium => write!(f, "medium"),
            Self::Low => write!(f, "low"),
        }
    }
}

impl Ord for NodeCriticality {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        self.weight().cmp(&other.weight())
    }
}

impl PartialOrd for NodeCriticality {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

// ---------------------------------------------------------------------------
// LoadPolicy
// ---------------------------------------------------------------------------

/// Determines when and how a node is loaded into RAM.
///
/// This is the core mechanism for the fractal DAG's memory management:
/// only nodes that are needed are loaded, and idle nodes are evicted.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LoadPolicy {
    /// Always resident in RAM. Reserved for core orchestrator nodes.
    Always,
    /// Loaded when the parent super-node is activated.
    OnDemand,
    /// Cached after first use; evictable under memory pressure.
    Cache,
    /// Only loaded on explicit request (rarely used capabilities).
    Lazy,
}

impl fmt::Display for LoadPolicy {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Always => write!(f, "always"),
            Self::OnDemand => write!(f, "on_demand"),
            Self::Cache => write!(f, "cache"),
            Self::Lazy => write!(f, "lazy"),
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
    fn criticality_ordering() {
        assert!(NodeCriticality::Critical > NodeCriticality::High);
        assert!(NodeCriticality::High > NodeCriticality::Medium);
        assert!(NodeCriticality::Medium > NodeCriticality::Low);
    }

    #[test]
    fn criticality_weight_consistency() {
        assert!(NodeCriticality::Critical.weight() > NodeCriticality::High.weight());
        assert!(NodeCriticality::High.weight() > NodeCriticality::Medium.weight());
        assert!(NodeCriticality::Medium.weight() > NodeCriticality::Low.weight());
    }

    #[test]
    fn category_display_roundtrip() {
        for cat in NodeCategory::all() {
            let s = cat.to_string();
            assert!(!s.is_empty(), "empty display for {:?}", cat);
        }
    }

    #[test]
    fn load_policy_variants_distinct() {
        let policies = [LoadPolicy::Always, LoadPolicy::OnDemand, LoadPolicy::Cache, LoadPolicy::Lazy];
        let displays: Vec<String> = policies.iter().map(|p| p.to_string()).collect();
        let mut unique = displays.clone();
        unique.dedup();
        assert_eq!(displays.len(), unique.len());
    }

    #[test]
    fn node_category_count() {
        assert_eq!(NodeCategory::all().len(), 17);
    }
}
