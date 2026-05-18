//! FractalLoader methods: queries, loading, unloading.

use zenic_graph::NodeCatalog;
use zenic_proto::{LoadPolicy, SubGraphId, SuperNodeId};

use crate::errors::RuntimeError;
use crate::memory::MemoryManager;

use super::types::{FractalLoader, SubGraphEntry, SubGraphLoadState};

impl FractalLoader {
    // -----------------------------------------------------------------------
    // Queries
    // -----------------------------------------------------------------------

    /// Whether a subgraph is currently loaded.
    pub fn is_loaded(&self, sub_graph_id: &SubGraphId) -> bool {
        self.loaded.contains_key(sub_graph_id)
    }

    /// Returns the number of currently loaded subgraphs.
    pub fn loaded_count(&self) -> usize {
        self.loaded.len()
    }

    /// Returns the state of a subgraph.
    pub fn state(&self, sub_graph_id: &SubGraphId) -> SubGraphLoadState {
        if self.loaded.contains_key(sub_graph_id) {
            SubGraphLoadState::Loaded
        } else {
            SubGraphLoadState::Unloaded
        }
    }

    /// Returns all currently loaded subgraph IDs.
    pub fn loaded_sub_graph_ids(&self) -> Vec<SubGraphId> {
        self.loaded.keys().copied().collect()
    }

    /// Returns all loaded subgraphs belonging to a super-node.
    pub fn loaded_by_super_node(&self, super_node_id: &SuperNodeId) -> Vec<SubGraphId> {
        self.loaded
            .values()
            .filter(|e| e.super_node_id == *super_node_id)
            .map(|e| e.sub_graph_id)
            .collect()
    }

    // -----------------------------------------------------------------------
    // Loading
    // -----------------------------------------------------------------------

    /// Loads a subgraph into RAM.
    pub fn load_sub_graph(
        &mut self,
        sub_graph_id: SubGraphId,
        catalog: &NodeCatalog,
        memory_manager: &mut MemoryManager,
    ) -> Result<(), RuntimeError> {
        // Idempotent: already loaded.
        if self.loaded.contains_key(&sub_graph_id) {
            return Ok(());
        }

        let sg_desc = catalog
            .get_sub_graph(&sub_graph_id)
            .ok_or(RuntimeError::SubGraphNotFound(sub_graph_id))?;

        let mut loaded_nodes: Vec<(zenic_proto::NodeId, u64, Option<SubGraphId>, LoadPolicy)> =
            Vec::new();
        let mut total_memory = 0u64;

        for node_id in &sg_desc.node_ids {
            let node_desc = catalog
                .get_node(node_id)
                .ok_or(RuntimeError::NodeNotLoaded(*node_id))?;

            let result = memory_manager.load_node(
                *node_id,
                node_desc.memory_estimate_bytes,
                Some(sub_graph_id),
                node_desc.load_policy,
            );

            match result {
                Ok(()) => {
                    loaded_nodes.push((
                        *node_id,
                        node_desc.memory_estimate_bytes,
                        Some(sub_graph_id),
                        node_desc.load_policy,
                    ));
                    total_memory += node_desc.memory_estimate_bytes;
                }
                Err(e) => {
                    // Rollback: evict all nodes we just loaded.
                    for (nid, _, _, _) in &loaded_nodes {
                        let _ = memory_manager.evict_node(nid);
                    }
                    return Err(RuntimeError::SubGraphLoadFailed {
                        sub_graph_id,
                        message: format!(
                            "failed to load node {}: {}",
                            node_id, e
                        ),
                    });
                }
            }
        }

        self.loaded.insert(
            sub_graph_id,
            SubGraphEntry {
                sub_graph_id,
                super_node_id: sg_desc.super_node_id,
                total_memory_bytes: total_memory,
                node_count: sg_desc.node_ids.len(),
                last_accessed: std::time::Instant::now(),
            },
        );

        Ok(())
    }

    /// Unloads a subgraph from RAM.
    pub fn unload_sub_graph(
        &mut self,
        sub_graph_id: &SubGraphId,
        memory_manager: &mut MemoryManager,
    ) -> Result<u64, RuntimeError> {
        if !self.loaded.contains_key(sub_graph_id) {
            return Ok(0); // Already unloaded, idempotent.
        }

        let freed = memory_manager.evict_sub_graph(sub_graph_id);
        self.loaded.remove(sub_graph_id);
        Ok(freed)
    }

    /// Unloads all subgraphs belonging to a super-node.
    pub fn unload_super_node(
        &mut self,
        super_node_id: &SuperNodeId,
        memory_manager: &mut MemoryManager,
    ) -> u64 {
        let sub_graph_ids: Vec<SubGraphId> = self
            .loaded
            .values()
            .filter(|e| e.super_node_id == *super_node_id)
            .map(|e| e.sub_graph_id)
            .collect();

        let mut total_freed = 0u64;
        for sg_id in sub_graph_ids {
            let freed = memory_manager.evict_sub_graph(&sg_id);
            self.loaded.remove(&sg_id);
            total_freed += freed;
        }
        total_freed
    }

    /// Finds the LRU subgraph for eviction.
    pub fn find_lru_sub_graph(&self) -> Option<SubGraphId> {
        self.loaded
            .values()
            .min_by_key(|e| e.last_accessed)
            .map(|e| e.sub_graph_id)
    }

    /// Touches a subgraph to update its LRU timestamp.
    pub fn touch(&mut self, sub_graph_id: &SubGraphId) {
        if let Some(entry) = self.loaded.get_mut(sub_graph_id) {
            entry.last_accessed = std::time::Instant::now();
        }
    }
}
