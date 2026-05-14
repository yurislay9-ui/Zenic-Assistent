//! Sub-graph (subgrafo) descriptor for the fractal DAG.
//!
//! A sub-graph is a certified, self-contained sub-DAG within a super-node.
//! Sub-graphs are the unit of lazy loading: only active subgraphs are in RAM.

use serde::{Deserialize, Serialize};
use zenic_proto::{BusinessDomain, LoadPolicy, NodeCriticality, NodeId, SubGraphId, SuperNodeId};

/// Maximum number of leaf nodes a sub-graph can contain.
/// Keeps mobile RAM bounded: each node is lightweight but we need limits.
pub const MAX_NODES_PER_SUBGRAPH: usize = 15;

/// Descriptor for a certified sub-graph in the fractal DAG.
///
/// Sub-graphs are the primary unit of on-demand loading. When a super-node
/// is activated, the runtime loads only the sub-graphs required for the
/// current task. Idle sub-graphs are serialized to disk (bincode + zstd).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SubGraphDescriptor {
    /// Unique identifier.
    pub id: SubGraphId,
    /// Canonical name (e.g., "ecommerce_inventory", "finance_invoicing").
    pub name: String,
    /// Business domain.
    pub domain: BusinessDomain,
    /// Short description.
    pub description: String,
    /// Parent super-node.
    pub super_node_id: SuperNodeId,
    /// IDs of the leaf nodes contained in this sub-graph.
    pub node_ids: Vec<NodeId>,
    /// IDs of nodes that serve as entry points into this sub-graph.
    pub entry_node_ids: Vec<NodeId>,
    /// IDs of nodes that serve as exit points from this sub-graph.
    pub exit_node_ids: Vec<NodeId>,
    /// Load policy.
    pub load_policy: LoadPolicy,
    /// Criticality of this sub-graph.
    pub criticality: NodeCriticality,
    /// Estimated memory when loaded (bytes).
    pub memory_estimate_bytes: u64,
    /// Semantic version of this sub-graph's structure.
    pub version: String,
}

impl SubGraphDescriptor {
    /// Validates the sub-graph descriptor for internal consistency.
    pub fn validate(&self) -> Result<(), String> {
        if self.name.is_empty() {
            return Err(format!("sub-graph {} has empty name", self.id));
        }
        if self.version.is_empty() {
            return Err(format!("sub-graph {} '{}' has empty version", self.id, self.name));
        }
        if self.node_ids.is_empty() {
            return Err(format!(
                "sub-graph {} '{}' has no nodes",
                self.id, self.name
            ));
        }
        if self.node_ids.len() > MAX_NODES_PER_SUBGRAPH {
            return Err(format!(
                "sub-graph {} '{}' has {} nodes (max {})",
                self.id,
                self.name,
                self.node_ids.len(),
                MAX_NODES_PER_SUBGRAPH
            ));
        }
        if self.entry_node_ids.is_empty() {
            return Err(format!(
                "sub-graph {} '{}' has no entry nodes",
                self.id, self.name
            ));
        }
        // Every entry node must be in node_ids.
        for entry_id in &self.entry_node_ids {
            if !self.node_ids.contains(entry_id) {
                return Err(format!(
                    "sub-graph {} '{}' entry node {} not in node_ids",
                    self.id, self.name, entry_id
                ));
            }
        }
        // Every exit node must be in node_ids.
        for exit_id in &self.exit_node_ids {
            if !self.node_ids.contains(exit_id) {
                return Err(format!(
                    "sub-graph {} '{}' exit node {} not in node_ids",
                    self.id, self.name, exit_id
                ));
            }
        }
        if self.memory_estimate_bytes == 0 {
            return Err(format!(
                "sub-graph {} '{}' has zero memory estimate",
                self.id, self.name
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

    fn valid_subgraph() -> SubGraphDescriptor {
        let entry = NodeId::new();
        let exit = NodeId::new();
        SubGraphDescriptor {
            id: SubGraphId::new(),
            name: "ecommerce_inventory".to_string(),
            domain: BusinessDomain::ECommerce,
            description: "Inventory tracking and reorder management".to_string(),
            super_node_id: SuperNodeId::new(),
            node_ids: vec![entry, exit],
            entry_node_ids: vec![entry],
            exit_node_ids: vec![exit],
            load_policy: LoadPolicy::OnDemand,
            criticality: NodeCriticality::Medium,
            memory_estimate_bytes: 2048,
            version: "1.0.0".to_string(),
        }
    }

    #[test]
    fn valid_subgraph_passes_validation() {
        assert!(valid_subgraph().validate().is_ok());
    }

    #[test]
    fn empty_name_fails() {
        let mut sg = valid_subgraph();
        sg.name = String::new();
        assert!(sg.validate().is_err());
    }

    #[test]
    fn empty_version_fails() {
        let mut sg = valid_subgraph();
        sg.version = String::new();
        assert!(sg.validate().is_err());
    }

    #[test]
    fn no_nodes_fails() {
        let mut sg = valid_subgraph();
        sg.node_ids = vec![];
        sg.entry_node_ids = vec![];
        sg.exit_node_ids = vec![];
        assert!(sg.validate().is_err());
    }

    #[test]
    fn no_entry_nodes_fails() {
        let mut sg = valid_subgraph();
        sg.entry_node_ids = vec![];
        assert!(sg.validate().is_err());
    }

    #[test]
    fn entry_not_in_node_ids_fails() {
        let mut sg = valid_subgraph();
        sg.entry_node_ids = vec![NodeId::new()]; // Not in node_ids
        assert!(sg.validate().is_err());
    }

    #[test]
    fn exit_not_in_node_ids_fails() {
        let mut sg = valid_subgraph();
        sg.exit_node_ids = vec![NodeId::new()]; // Not in node_ids
        assert!(sg.validate().is_err());
    }

    #[test]
    fn zero_memory_fails() {
        let mut sg = valid_subgraph();
        sg.memory_estimate_bytes = 0;
        assert!(sg.validate().is_err());
    }

    #[test]
    fn too_many_nodes_fails() {
        let mut sg = valid_subgraph();
        sg.node_ids = (0..MAX_NODES_PER_SUBGRAPH + 1).map(|_| NodeId::new()).collect();
        sg.entry_node_ids = vec![sg.node_ids[0]];
        sg.exit_node_ids = vec![sg.node_ids[1]];
        assert!(sg.validate().is_err());
    }
}
