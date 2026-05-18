//! Memory manager types, constants, and NodeLoadState definition.

use zenic_proto::NodeId;

/// Default maximum number of nodes that can be loaded simultaneously.
pub const DEFAULT_MAX_LOADED_NODES: usize = 25;

/// Default memory budget in bytes (50 MB).
pub const DEFAULT_MEMORY_BUDGET_BYTES: u64 = 50 * 1024 * 1024;

/// Current load state of a node in memory.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum NodeLoadState {
    /// Node is resident in RAM and available for execution.
    Loaded,
    /// Node is currently executing (cannot be evicted).
    Executing,
    /// Node has been evicted from RAM (only metadata available).
    Evicted,
}

impl std::fmt::Display for NodeLoadState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Loaded => write!(f, "loaded"),
            Self::Executing => write!(f, "executing"),
            Self::Evicted => write!(f, "evicted"),
        }
    }
}

/// Internal tracking record for a loaded node.
#[derive(Debug, Clone)]
pub(crate) struct NodeMemoryEntry {
    /// Estimated memory footprint in bytes.
    pub(crate) memory_bytes: u64,
    /// Current load state.
    pub(crate) state: NodeLoadState,
    /// Which sub-graph this node belongs to (for group eviction).
    pub(crate) sub_graph_id: Option<zenic_proto::SubGraphId>,
    /// Last access timestamp (monotonic counter for LRU).
    pub(crate) last_access: u64,
}

/// Tracks which nodes are in RAM and enforces memory budgets.
pub struct MemoryManager {
    /// Maximum number of nodes that can be loaded at once.
    pub(crate) max_loaded_nodes: usize,
    /// Maximum total memory budget in bytes.
    pub(crate) memory_budget_bytes: u64,
    /// Currently tracked nodes.
    pub(crate) entries: std::collections::HashMap<NodeId, NodeMemoryEntry>,
    /// Monotonic counter for LRU ordering.
    pub(crate) access_counter: u64,
    /// Current total memory usage in bytes.
    pub(crate) current_usage_bytes: u64,
}
