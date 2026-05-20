//! Criticality gate builder: configure custom thresholds before building.

use indexmap::IndexMap;
use zenic_proto::NodeCriticality;
use crate::role::CriticalityClearance;

use super::types::CriticalityGate;

// ---------------------------------------------------------------------------
// CriticalityGateBuilder
// ---------------------------------------------------------------------------

/// Builder for constructing a [`CriticalityGate`] with custom thresholds.
///
/// Security boundaries (clearance thresholds) must be configured *before*
/// the gate is built. Once built, the gate is immutable. This prevents
/// runtime weakening of security boundaries — the same principle as
/// [`SafetyVeto`](super::types::SafetyVeto).
///
/// # Example
///
/// ```ignore
/// let gate = CriticalityGateBuilder::new()
///     .threshold(NodeCriticality::Low, CriticalityClearance::Critical)
///     .build();
/// ```
pub struct CriticalityGateBuilder {
    thresholds: IndexMap<NodeCriticality, CriticalityClearance>,
}

impl CriticalityGateBuilder {
    /// Creates a builder pre-populated with the default thresholds.
    pub fn new() -> Self {
        let mut thresholds = IndexMap::new();
        thresholds.insert(NodeCriticality::Low, CriticalityClearance::Low);
        thresholds.insert(NodeCriticality::Medium, CriticalityClearance::Medium);
        thresholds.insert(NodeCriticality::High, CriticalityClearance::High);
        thresholds.insert(NodeCriticality::Critical, CriticalityClearance::Critical);
        Self { thresholds }
    }

    /// Sets the clearance threshold for a specific criticality level.
    ///
    /// Can be called multiple times — last call wins for a given level.
    pub fn threshold(mut self, criticality: NodeCriticality, clearance: CriticalityClearance) -> Self {
        self.thresholds.insert(criticality, clearance);
        self
    }

    /// Builds the immutable [`CriticalityGate`].
    pub fn build(self) -> CriticalityGate {
        CriticalityGate {
            thresholds: self.thresholds,
        }
    }
}

impl Default for CriticalityGateBuilder {
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
    use crate::role::{CriticalityClearance, Role};
    use crate::gate::types::CriticalityGate;
    use zenic_proto::{NodeId, NodeCriticality, SessionId};

    #[test]
    fn criticality_gate_custom_threshold() {
        // Use the builder to configure custom thresholds at construction time.
        // Require Critical clearance even for Low criticality.
        let gate = CriticalityGateBuilder::new()
            .threshold(NodeCriticality::Low, CriticalityClearance::Critical)
            .build();
        let medium_role = Role::new("operator", "Operator").with_clearance(CriticalityClearance::Medium);
        let roles = vec![&medium_role];
        let result = gate.check(
            &roles,
            NodeCriticality::Low,
            SessionId::new(),
            NodeId::new(),
        );
        assert!(result.is_err());
    }

    #[test]
    fn criticality_gate_builder_default_is_new() {
        let builder = CriticalityGateBuilder::default();
        let gate = builder.build();
        // Should behave the same as CriticalityGate::new()
        let role = Role::new("admin", "Admin").with_clearance(CriticalityClearance::Critical);
        let roles = vec![&role];
        let result = gate.check(&roles, NodeCriticality::Low, SessionId::new(), NodeId::new());
        assert!(result.is_ok());
    }
}
