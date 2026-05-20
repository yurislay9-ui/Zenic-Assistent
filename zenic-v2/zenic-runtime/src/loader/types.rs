//! FractalLoader types and struct definition.

use std::collections::HashMap;
use std::time::Instant;
use zenic_proto::SubGraphId;
use zenic_graph::NodeCatalog;
use zenic_proto::SuperNodeId;

/// Current state of a subgraph in memory.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SubGraphLoadState {
    /// Subgraph is loaded and available for execution.
    Loaded,
    /// Subgraph is on disk and not in RAM.
    Unloaded,
}

/// Internal tracking record for a loaded subgraph.
#[derive(Debug, Clone)]
pub(crate) struct SubGraphEntry {
    /// The subgraph ID.
    pub(crate) sub_graph_id: SubGraphId,
    /// The parent super-node.
    pub(crate) super_node_id: SuperNodeId,
    /// Total estimated memory of all nodes in this subgraph.
    #[allow(dead_code)]
    pub(crate) total_memory_bytes: u64,
    /// Number of nodes in this subgraph.
    #[allow(dead_code)]
    pub(crate) node_count: usize,
    /// When this subgraph was last accessed.
    pub(crate) last_accessed: Instant,
}

/// Manages on-demand loading and unloading of fractal subgraphs.
pub struct FractalLoader {
    /// Currently loaded subgraphs.
    pub(crate) loaded: HashMap<SubGraphId, SubGraphEntry>,
}

impl FractalLoader {
    /// Creates a new empty loader.
    pub fn new() -> Self {
        Self {
            loaded: HashMap::new(),
        }
    }
}

impl Default for FractalLoader {
    fn default() -> Self {
        Self::new()
    }
}
