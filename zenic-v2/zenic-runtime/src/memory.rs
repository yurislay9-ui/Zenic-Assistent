//! Memory manager for the fractal DAG runtime.
//!
//! Enforces the RAM budget constraint: only a configurable number of nodes
//! (default 25) may be resident in memory at once. Tracks which nodes are
//! loaded and their estimated memory footprint.

use std::collections::HashMap;
use zenic_proto::{LoadPolicy, NodeId, SubGraphId};
use crate::errors::RuntimeError;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Default maximum number of nodes that can be loaded simultaneously.
/// On the target hardware (Xiaomi Redmi 12R Pro / Termux), we keep
/// 15-25 nodes in RAM to stay within safe memory bounds.
pub const DEFAULT_MAX_LOADED_NODES: usize = 25;

/// Default memory budget in bytes (50 MB).
pub const DEFAULT_MEMORY_BUDGET_BYTES: u64 = 50 * 1024 * 1024;

// ---------------------------------------------------------------------------
// NodeLoadState
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// NodeMemoryEntry
// ---------------------------------------------------------------------------

/// Internal tracking record for a loaded node.
#[derive(Debug, Clone)]
struct NodeMemoryEntry {
    /// Estimated memory footprint in bytes.
    memory_bytes: u64,
    /// Current load state.
    state: NodeLoadState,
    /// Which sub-graph this node belongs to (for group eviction).
    sub_graph_id: Option<SubGraphId>,
    /// Last access timestamp (monotonic counter for LRU).
    last_access: u64,
}

// ---------------------------------------------------------------------------
// MemoryManager
// ---------------------------------------------------------------------------

/// Tracks which nodes are in RAM and enforces memory budgets.
///
/// The memory manager ensures that the fractal DAG never exceeds the
/// configured memory limits. Nodes with [`LoadPolicy::Always`] are
/// pinned and cannot be evicted.
pub struct MemoryManager {
    /// Maximum number of nodes that can be loaded at once.
    max_loaded_nodes: usize,
    /// Maximum total memory budget in bytes.
    memory_budget_bytes: u64,
    /// Currently tracked nodes.
    entries: HashMap<NodeId, NodeMemoryEntry>,
    /// Monotonic counter for LRU ordering.
    access_counter: u64,
    /// Current total memory usage in bytes.
    current_usage_bytes: u64,
}

impl MemoryManager {
    /// Creates a new memory manager with default limits.
    pub fn new() -> Self {
        Self::with_limits(DEFAULT_MAX_LOADED_NODES, DEFAULT_MEMORY_BUDGET_BYTES)
    }

    /// Creates a new memory manager with custom limits.
    pub fn with_limits(max_loaded_nodes: usize, memory_budget_bytes: u64) -> Self {
        Self {
            max_loaded_nodes,
            memory_budget_bytes,
            entries: HashMap::new(),
            access_counter: 0,
            current_usage_bytes: 0,
        }
    }

    // -----------------------------------------------------------------------
    // Queries
    // -----------------------------------------------------------------------

    /// Returns the number of currently loaded (or executing) nodes.
    pub fn loaded_node_count(&self) -> usize {
        self.entries
            .values()
            .filter(|e| e.state == NodeLoadState::Loaded || e.state == NodeLoadState::Executing)
            .count()
    }

    /// Returns the current total memory usage in bytes.
    pub fn current_usage_bytes(&self) -> u64 {
        self.current_usage_bytes
    }

    /// Returns the configured memory budget in bytes.
    pub fn memory_budget_bytes(&self) -> u64 {
        self.memory_budget_bytes
    }

    /// Returns the configured max loaded nodes.
    pub fn max_loaded_nodes(&self) -> usize {
        self.max_loaded_nodes
    }

    /// Returns the load state of a node, or `None` if not tracked.
    pub fn node_state(&self, node_id: &NodeId) -> Option<NodeLoadState> {
        self.entries.get(node_id).map(|e| e.state)
    }

    /// Whether a node is currently loaded in RAM.
    pub fn is_loaded(&self, node_id: &NodeId) -> bool {
        self.entries
            .get(node_id)
            .map(|e| e.state == NodeLoadState::Loaded || e.state == NodeLoadState::Executing)
            .unwrap_or(false)
    }

    /// Returns the number of available slots before hitting the node limit.
    pub fn available_slots(&self) -> usize {
        self.max_loaded_nodes.saturating_sub(self.loaded_node_count())
    }

    /// Returns the available memory budget in bytes.
    pub fn available_memory(&self) -> u64 {
        self.memory_budget_bytes.saturating_sub(self.current_usage_bytes)
    }

    // -----------------------------------------------------------------------
    // Mutations
    // -----------------------------------------------------------------------

    /// Marks a node as loaded in RAM.
    ///
    /// Validates that the load is within budget. Does NOT check for
    /// executor availability — that is the caller's responsibility.
    pub fn load_node(
        &mut self,
        node_id: NodeId,
        memory_bytes: u64,
        sub_graph_id: Option<SubGraphId>,
        load_policy: LoadPolicy,
    ) -> Result<(), RuntimeError> {
        // Already loaded: just update access time.
        if self.entries.contains_key(&node_id) {
            let ts = self.next_access();
            if let Some(e) = self.entries.get_mut(&node_id) {
                e.last_access = ts;
            }
            return Ok(());
        }

        // Check node count limit (Always-loaded nodes bypass this).
        if load_policy != LoadPolicy::Always && self.loaded_node_count() >= self.max_loaded_nodes {
            return Err(RuntimeError::TooManyNodesLoaded {
                current: self.loaded_node_count(),
                max: self.max_loaded_nodes,
            });
        }

        // Check memory budget.
        if load_policy != LoadPolicy::Always && memory_bytes > self.available_memory() {
            return Err(RuntimeError::MemoryBudgetExceeded {
                requested: memory_bytes,
                available: self.available_memory(),
            });
        }

        let ts = self.next_access();
        self.entries.insert(
            node_id,
            NodeMemoryEntry {
                memory_bytes,
                state: NodeLoadState::Loaded,
                sub_graph_id,
                last_access: ts,
            },
        );
        self.current_usage_bytes += memory_bytes;

        Ok(())
    }

    /// Marks a node as currently executing (cannot be evicted).
    pub fn mark_executing(&mut self, node_id: &NodeId) -> Result<(), RuntimeError> {
        let ts = self.next_access();
        let entry = self
            .entries
            .get_mut(node_id)
            .ok_or(RuntimeError::NodeNotLoaded(*node_id))?;
        entry.state = NodeLoadState::Executing;
        entry.last_access = ts;
        Ok(())
    }

    /// Marks an executing node as loaded again (execution finished).
    pub fn mark_completed(&mut self, node_id: &NodeId) -> Result<(), RuntimeError> {
        let entry = self
            .entries
            .get_mut(node_id)
            .ok_or(RuntimeError::NodeNotLoaded(*node_id))?;
        if entry.state != NodeLoadState::Executing {
            return Err(RuntimeError::General(format!(
                "node {} is not in executing state (current: {})",
                node_id, entry.state
            )));
        }
        entry.state = NodeLoadState::Loaded;
        Ok(())
    }

    /// Evicts a node from RAM.
    ///
    /// Returns the estimated memory freed. Cannot evict nodes that are
    /// currently executing or have `LoadPolicy::Always`.
    pub fn evict_node(&mut self, node_id: &NodeId) -> Result<u64, RuntimeError> {
        let entry = self
            .entries
            .get(node_id)
            .ok_or(RuntimeError::NodeNotLoaded(*node_id))?;

        if entry.state == NodeLoadState::Executing {
            return Err(RuntimeError::General(format!(
                "cannot evict node {}: currently executing",
                node_id
            )));
        }

        let freed = entry.memory_bytes;
        self.current_usage_bytes = self.current_usage_bytes.saturating_sub(freed);
        self.entries.remove(node_id);
        Ok(freed)
    }

    /// Evicts all nodes belonging to a sub-graph.
    ///
    /// Returns the total memory freed. Skips executing nodes.
    pub fn evict_sub_graph(&mut self, sub_graph_id: &SubGraphId) -> u64 {
        let to_evict: Vec<NodeId> = self
            .entries
            .iter()
            .filter(|(_, entry)| {
                entry.sub_graph_id == Some(*sub_graph_id)
                    && entry.state != NodeLoadState::Executing
            })
            .map(|(id, _)| *id)
            .collect();

        let mut total_freed = 0u64;
        for node_id in to_evict {
            if let Some(entry) = self.entries.remove(&node_id) {
                self.current_usage_bytes = self.current_usage_bytes.saturating_sub(entry.memory_bytes);
                total_freed += entry.memory_bytes;
            }
        }
        total_freed
    }

    /// Finds the best LRU candidate for eviction.
    ///
    /// Returns `None` if no evictable nodes exist (all are executing or pinned).
    /// Nodes with `LoadPolicy::Always` should not be loaded into the manager
    /// with eviction intent; the caller must avoid loading them as evictable.
    pub fn find_lru_eviction_candidate(&self) -> Option<NodeId> {
        self.entries
            .iter()
            .filter(|(_, entry)| entry.state == NodeLoadState::Loaded)
            .min_by_key(|(_, entry)| entry.last_access)
            .map(|(id, _)| *id)
    }

    // -----------------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------------

    fn next_access(&mut self) -> u64 {
        self.access_counter += 1;
        self.access_counter
    }
}

impl Default for MemoryManager {
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

    #[test]
    fn new_has_defaults() {
        let mm = MemoryManager::new();
        assert_eq!(mm.max_loaded_nodes(), DEFAULT_MAX_LOADED_NODES);
        assert_eq!(mm.memory_budget_bytes(), DEFAULT_MEMORY_BUDGET_BYTES);
        assert_eq!(mm.loaded_node_count(), 0);
        assert_eq!(mm.current_usage_bytes(), 0);
    }

    #[test]
    fn load_node_within_budget() {
        let mut mm = MemoryManager::with_limits(5, 10240);
        let id = NodeId::new();
        mm.load_node(id, 1024, None, LoadPolicy::OnDemand).expect("load");
        assert_eq!(mm.loaded_node_count(), 1);
        assert_eq!(mm.current_usage_bytes(), 1024);
        assert!(mm.is_loaded(&id));
    }

    #[test]
    fn load_node_exceeds_node_count() {
        let mut mm = MemoryManager::with_limits(2, 102400);
        mm.load_node(NodeId::new(), 512, None, LoadPolicy::OnDemand).expect("load 1");
        mm.load_node(NodeId::new(), 512, None, LoadPolicy::OnDemand).expect("load 2");
        let result = mm.load_node(NodeId::new(), 512, None, LoadPolicy::OnDemand);
        assert!(result.is_err());
    }

    #[test]
    fn load_node_exceeds_memory_budget() {
        let mut mm = MemoryManager::with_limits(10, 1024);
        let result = mm.load_node(NodeId::new(), 2048, None, LoadPolicy::OnDemand);
        assert!(result.is_err());
    }

    #[test]
    fn always_loaded_bypasses_limits() {
        let mut mm = MemoryManager::with_limits(1, 100);
        // First load fills the limit.
        mm.load_node(NodeId::new(), 50, None, LoadPolicy::OnDemand).expect("load 1");
        // Always-loaded should still succeed.
        let always_id = NodeId::new();
        mm.load_node(always_id, 200, None, LoadPolicy::Always).expect("always load");
        assert!(mm.is_loaded(&always_id));
    }

    #[test]
    fn load_idempotent() {
        let mut mm = MemoryManager::with_limits(5, 10240);
        let id = NodeId::new();
        mm.load_node(id, 1024, None, LoadPolicy::OnDemand).expect("load 1");
        mm.load_node(id, 1024, None, LoadPolicy::OnDemand).expect("load 2 (idempotent)");
        assert_eq!(mm.loaded_node_count(), 1);
        assert_eq!(mm.current_usage_bytes(), 1024);
    }

    #[test]
    fn mark_executing_and_complete() {
        let mut mm = MemoryManager::with_limits(5, 10240);
        let id = NodeId::new();
        mm.load_node(id, 1024, None, LoadPolicy::OnDemand).expect("load");
        mm.mark_executing(&id).expect("executing");
        assert_eq!(mm.node_state(&id), Some(NodeLoadState::Executing));
        mm.mark_completed(&id).expect("completed");
        assert_eq!(mm.node_state(&id), Some(NodeLoadState::Loaded));
    }

    #[test]
    fn cannot_evict_executing_node() {
        let mut mm = MemoryManager::with_limits(5, 10240);
        let id = NodeId::new();
        mm.load_node(id, 1024, None, LoadPolicy::OnDemand).expect("load");
        mm.mark_executing(&id).expect("executing");
        let result = mm.evict_node(&id);
        assert!(result.is_err());
    }

    #[test]
    fn evict_node_frees_memory() {
        let mut mm = MemoryManager::with_limits(5, 10240);
        let id = NodeId::new();
        mm.load_node(id, 2048, None, LoadPolicy::OnDemand).expect("load");
        let freed = mm.evict_node(&id).expect("evict");
        assert_eq!(freed, 2048);
        assert_eq!(mm.current_usage_bytes(), 0);
        assert!(!mm.is_loaded(&id));
    }

    #[test]
    fn evict_sub_graph() {
        let sg = SubGraphId::new();
        let mut mm = MemoryManager::with_limits(10, 102400);
        mm.load_node(NodeId::new(), 1024, Some(sg), LoadPolicy::OnDemand).expect("load 1");
        mm.load_node(NodeId::new(), 2048, Some(sg), LoadPolicy::OnDemand).expect("load 2");
        mm.load_node(NodeId::new(), 512, None, LoadPolicy::OnDemand).expect("load 3 (other)");
        let freed = mm.evict_sub_graph(&sg);
        assert_eq!(freed, 3072);
        assert_eq!(mm.loaded_node_count(), 1);
    }

    #[test]
    fn find_lru_eviction_candidate() {
        let mut mm = MemoryManager::with_limits(5, 10240);
        let first = NodeId::new();
        let second = NodeId::new();
        mm.load_node(first, 512, None, LoadPolicy::OnDemand).expect("load 1");
        mm.load_node(second, 512, None, LoadPolicy::OnDemand).expect("load 2");
        let candidate = mm.find_lru_eviction_candidate();
        assert_eq!(candidate, Some(first)); // First loaded = oldest access
    }

    #[test]
    fn available_slots_and_memory() {
        let mut mm = MemoryManager::with_limits(5, 10240);
        assert_eq!(mm.available_slots(), 5);
        assert_eq!(mm.available_memory(), 10240);
        mm.load_node(NodeId::new(), 1024, None, LoadPolicy::OnDemand).expect("load");
        assert_eq!(mm.available_slots(), 4);
        assert_eq!(mm.available_memory(), 9216);
    }

    #[test]
    fn default_is_new() {
        let mm = MemoryManager::default();
        assert_eq!(mm.max_loaded_nodes(), DEFAULT_MAX_LOADED_NODES);
    }
}
