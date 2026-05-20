//! NodeCatalog struct definition and construction.

use indexmap::IndexMap;
use zenic_proto::{BusinessDomain, NodeId, SubGraphId, SuperNodeId};

use crate::descriptor::NodeDescriptor;
use crate::subgraph::SubGraphDescriptor;
use crate::supernode::SuperNodeDescriptor;

/// In-memory catalog of all graph descriptors.
///
/// The catalog is the single source of truth for what nodes, super-nodes,
/// and sub-graphs exist in the system.
pub struct NodeCatalog {
    /// Node descriptors indexed by NodeId (insertion-ordered).
    pub(crate) nodes: IndexMap<NodeId, NodeDescriptor>,
    /// Super-node descriptors indexed by SuperNodeId.
    pub(crate) super_nodes: IndexMap<SuperNodeId, SuperNodeDescriptor>,
    /// Sub-graph descriptors indexed by SubGraphId.
    pub(crate) sub_graphs: IndexMap<SubGraphId, SubGraphDescriptor>,
    /// Quick lookup: domain -> super-node IDs.
    pub(crate) domain_index: IndexMap<BusinessDomain, Vec<SuperNodeId>>,
}

impl NodeCatalog {
    /// Creates an empty catalog.
    pub fn new() -> Self {
        Self {
            nodes: IndexMap::new(),
            super_nodes: IndexMap::new(),
            sub_graphs: IndexMap::new(),
            domain_index: IndexMap::new(),
        }
    }
}

impl Default for NodeCatalog {
    fn default() -> Self {
        Self::new()
    }
}
