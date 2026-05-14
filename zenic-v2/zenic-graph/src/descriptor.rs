//! Node and edge descriptors for the fractal DAG.
//!
//! Descriptors are immutable metadata records that describe a node or edge
//! in the graph. They are stored in the catalog and used by the runtime
//! to instantiate and connect nodes.

use serde::{Deserialize, Serialize};
use zenic_proto::{
    BusinessDomain, LoadPolicy, NodeCategory, NodeCriticality, NodeId, SubGraphId, SuperNodeId,
};

// ---------------------------------------------------------------------------
// NodeDescriptor
// ---------------------------------------------------------------------------

/// Full descriptor for a DAG node (leaf or internal).
///
/// This is the canonical metadata record stored in the [`NodeCatalog`](super::catalog::NodeCatalog).
/// It contains everything the runtime needs to decide whether, when, and how
/// to load and execute this node.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct NodeDescriptor {
    /// Unique identifier for this node.
    pub id: NodeId,
    /// Human-readable name (e.g., "ecommerce_inventory_check").
    pub name: String,
    /// Semantic version of this node's logic (e.g., "1.2.0").
    pub version: String,
    /// Functional category.
    pub category: NodeCategory,
    /// Business domain this node belongs to.
    pub domain: BusinessDomain,
    /// How critical this node is for the system.
    pub criticality: NodeCriticality,
    /// Memory load policy.
    pub load_policy: LoadPolicy,
    /// Estimated memory footprint in bytes when loaded.
    pub memory_estimate_bytes: u64,
    /// IDs of nodes this node depends on (must execute before this one).
    pub dependencies: Vec<NodeId>,
    /// ID of the super-node this node belongs to (if any).
    pub super_node_id: Option<SuperNodeId>,
    /// ID of the sub-graph this node belongs to (if any).
    pub sub_graph_id: Option<SubGraphId>,
    /// Whether this node requires external API access.
    pub requires_external_api: bool,
    /// Short description of what this node does.
    pub description: String,
}

impl NodeDescriptor {
    /// Validates the descriptor for internal consistency.
    ///
    /// Returns `Ok(())` if all invariants hold, or a descriptive error otherwise.
    pub fn validate(&self) -> Result<(), String> {
        if self.name.is_empty() {
            return Err(format!("node {} has empty name", self.id));
        }
        if self.version.is_empty() {
            return Err(format!("node {} '{}' has empty version", self.id, self.name));
        }
        if self.memory_estimate_bytes == 0 {
            return Err(format!(
                "node {} '{}' has zero memory estimate",
                self.id, self.name
            ));
        }
        // Always-loaded nodes must be Critical or High criticality.
        if self.load_policy == LoadPolicy::Always
            && self.criticality < NodeCriticality::High
        {
            return Err(format!(
                "node {} '{}' is Always-loaded but has criticality {:?} (must be High or Critical)",
                self.id, self.name, self.criticality
            ));
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// EdgeKind
// ---------------------------------------------------------------------------

/// The semantic kind of an edge between two nodes.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum EdgeKind {
    /// Data flows from source to target.
    Data,
    /// Control flow: source triggers target.
    Control,
    /// Conditional: source triggers target only if a condition is met.
    Conditional,
}

// ---------------------------------------------------------------------------
// EdgeDescriptor
// ---------------------------------------------------------------------------

/// Descriptor for a directed edge between two nodes.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EdgeDescriptor {
    /// Source node.
    pub from: NodeId,
    /// Target node.
    pub to: NodeId,
    /// Semantic kind of this edge.
    pub kind: EdgeKind,
    /// Optional label (e.g., the condition for a Conditional edge).
    pub label: Option<String>,
}

impl EdgeDescriptor {
    /// Creates a data-flow edge.
    pub fn data(from: NodeId, to: NodeId) -> Self {
        Self {
            from,
            to,
            kind: EdgeKind::Data,
            label: None,
        }
    }

    /// Creates a control-flow edge.
    pub fn control(from: NodeId, to: NodeId) -> Self {
        Self {
            from,
            to,
            kind: EdgeKind::Control,
            label: None,
        }
    }

    /// Creates a conditional edge with a label.
    pub fn conditional(from: NodeId, to: NodeId, label: String) -> Self {
        Self {
            from,
            to,
            kind: EdgeKind::Conditional,
            label: Some(label),
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_descriptor() -> NodeDescriptor {
        NodeDescriptor {
            id: NodeId::new(),
            name: "test_node".to_string(),
            version: "1.0.0".to_string(),
            category: NodeCategory::Decision,
            domain: BusinessDomain::ECommerce,
            criticality: NodeCriticality::High,
            load_policy: LoadPolicy::Always,
            memory_estimate_bytes: 1024,
            dependencies: vec![],
            super_node_id: None,
            sub_graph_id: None,
            requires_external_api: false,
            description: "A test node".to_string(),
        }
    }

    #[test]
    fn valid_descriptor_passes_validation() {
        assert!(valid_descriptor().validate().is_ok());
    }

    #[test]
    fn empty_name_fails_validation() {
        let mut d = valid_descriptor();
        d.name = String::new();
        assert!(d.validate().is_err());
    }

    #[test]
    fn empty_version_fails_validation() {
        let mut d = valid_descriptor();
        d.version = String::new();
        assert!(d.validate().is_err());
    }

    #[test]
    fn zero_memory_fails_validation() {
        let mut d = valid_descriptor();
        d.memory_estimate_bytes = 0;
        assert!(d.validate().is_err());
    }

    #[test]
    fn always_loaded_with_low_criticality_fails() {
        let mut d = valid_descriptor();
        d.load_policy = LoadPolicy::Always;
        d.criticality = NodeCriticality::Low;
        assert!(d.validate().is_err());
    }

    #[test]
    fn edge_descriptor_data() {
        let a = NodeId::new();
        let b = NodeId::new();
        let edge = EdgeDescriptor::data(a, b);
        assert_eq!(edge.kind, EdgeKind::Data);
        assert_eq!(edge.from, a);
        assert_eq!(edge.to, b);
    }

    #[test]
    fn edge_descriptor_conditional() {
        let a = NodeId::new();
        let b = NodeId::new();
        let edge = EdgeDescriptor::conditional(a, b, "amount > 1000".to_string());
        assert_eq!(edge.kind, EdgeKind::Conditional);
        assert_eq!(edge.label.as_deref(), Some("amount > 1000"));
    }
}
