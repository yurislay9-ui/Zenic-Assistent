//! Super-node (supernodo) descriptor for the fractal DAG.
//!
//! A super-node is the top-level grouping in the 3-level fractal hierarchy:
//! `SuperNode -> SubGraph -> Node (hoja)`.
//! Each super-node aggregates one or more certified subgraphs for a business domain.

use serde::{Deserialize, Serialize};
use zenic_proto::{
    BusinessDomain, LoadPolicy, NodeCriticality, SubGraphId, SuperNodeId,
};

/// Maximum number of subgraphs a super-node can contain.
/// This limit ensures bounded memory usage on mobile devices.
pub const MAX_SUBGRAPHS_PER_SUPERNODE: usize = 8;

/// Descriptor for a super-node in the fractal DAG.
///
/// Super-nodes are the top-level entry points for domain routing.
/// When a request enters the system, the hierarchical router first
/// determines which super-node(s) are relevant, then loads their
/// subgraphs on demand.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SuperNodeDescriptor {
    /// Unique identifier.
    pub id: SuperNodeId,
    /// Canonical name (e.g., "COMMERCE", "FINANCE").
    pub name: String,
    /// Business domain this super-node covers.
    pub domain: BusinessDomain,
    /// Short description of the super-node's purpose.
    pub description: String,
    /// IDs of the certified subgraphs contained in this super-node.
    pub sub_graph_ids: Vec<SubGraphId>,
    /// How critical this super-node is.
    pub criticality: NodeCriticality,
    /// Load policy for the entire super-node.
    pub load_policy: LoadPolicy,
    /// Estimated total memory when all subgraphs are loaded (bytes).
    pub memory_estimate_bytes: u64,
    /// Maximum number of subgraphs that can be active simultaneously.
    pub max_active_subgraphs: u8,
}

impl SuperNodeDescriptor {
    /// Validates the super-node descriptor for internal consistency.
    pub fn validate(&self) -> Result<(), String> {
        if self.name.is_empty() {
            return Err(format!("super-node {} has empty name", self.id));
        }
        if self.sub_graph_ids.len() > MAX_SUBGRAPHS_PER_SUPERNODE {
            return Err(format!(
                "super-node {} '{}' has {} subgraphs (max {})",
                self.id,
                self.name,
                self.sub_graph_ids.len(),
                MAX_SUBGRAPHS_PER_SUPERNODE
            ));
        }
        if self.memory_estimate_bytes == 0 {
            return Err(format!(
                "super-node {} '{}' has zero memory estimate",
                self.id, self.name
            ));
        }
        if self.max_active_subgraphs as usize > self.sub_graph_ids.len() {
            return Err(format!(
                "super-node {} '{}' allows {} active subgraphs but only has {} registered",
                self.id,
                self.name,
                self.max_active_subgraphs,
                self.sub_graph_ids.len()
            ));
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_supernode() -> SuperNodeDescriptor {
        SuperNodeDescriptor {
            id: SuperNodeId::new(),
            name: "COMMERCE".to_string(),
            domain: BusinessDomain::ECommerce,
            description: "E-commerce and retail operations".to_string(),
            sub_graph_ids: vec![SubGraphId::new(), SubGraphId::new()],
            criticality: NodeCriticality::High,
            load_policy: LoadPolicy::OnDemand,
            memory_estimate_bytes: 4096,
            max_active_subgraphs: 2,
        }
    }

    #[test]
    fn valid_supernode_passes_validation() {
        assert!(valid_supernode().validate().is_ok());
    }

    #[test]
    fn empty_name_fails() {
        let mut sn = valid_supernode();
        sn.name = String::new();
        assert!(sn.validate().is_err());
    }

    #[test]
    fn too_many_subgraphs_fails() {
        let mut sn = valid_supernode();
        sn.sub_graph_ids = (0..MAX_SUBGRAPHS_PER_SUPERNODE + 1)
            .map(|_| SubGraphId::new())
            .collect();
        assert!(sn.validate().is_err());
    }

    #[test]
    fn zero_memory_fails() {
        let mut sn = valid_supernode();
        sn.memory_estimate_bytes = 0;
        assert!(sn.validate().is_err());
    }

    #[test]
    fn max_active_exceeds_registered_fails() {
        let mut sn = valid_supernode();
        sn.max_active_subgraphs = 10; // More than the 2 sub_graph_ids
        assert!(sn.validate().is_err());
    }
}
