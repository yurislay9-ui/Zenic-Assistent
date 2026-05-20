//! MemoryManager construction, queries, and mutations.

use std::collections::HashMap;
use zenic_proto::{LoadPolicy, NodeId, SubGraphId};
use crate::errors::RuntimeError;

use super::types::{
    DEFAULT_MAX_LOADED_NODES, DEFAULT_MEMORY_BUDGET_BYTES,
    MemoryManager, NodeLoadState, NodeMemoryEntry,
};

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
