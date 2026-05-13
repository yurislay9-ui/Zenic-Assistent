//! Fractal loader for on-demand subgraph loading/unloading.
//!
//! The [`FractalLoader`] manages which subgraphs are loaded into RAM.
//! It cooperates with the [`MemoryManager`](super::memory::MemoryManager)
//! to enforce memory budgets and evicts idle subgraphs using LRU policy.

use std::collections::HashMap;
use std::time::Instant;
use zenic_graph::NodeCatalog;
use zenic_proto::{LoadPolicy, SubGraphId, SuperNodeId};

use crate::errors::RuntimeError;
use crate::memory::MemoryManager;

// ---------------------------------------------------------------------------
// SubGraphLoadState
// ---------------------------------------------------------------------------

/// Current state of a subgraph in memory.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SubGraphLoadState {
    /// Subgraph is loaded and available for execution.
    Loaded,
    /// Subgraph is on disk and not in RAM.
    Unloaded,
}

// ---------------------------------------------------------------------------
// SubGraphEntry
// ---------------------------------------------------------------------------

/// Internal tracking record for a loaded subgraph.
#[derive(Debug, Clone)]
struct SubGraphEntry {
    /// The subgraph ID.
    sub_graph_id: SubGraphId,
    /// The parent super-node.
    super_node_id: SuperNodeId,
    /// Total estimated memory of all nodes in this subgraph.
    #[allow(dead_code)]
    total_memory_bytes: u64,
    /// Number of nodes in this subgraph.
    #[allow(dead_code)]
    node_count: usize,
    /// When this subgraph was last accessed.
    last_accessed: Instant,
}

// ---------------------------------------------------------------------------
// FractalLoader
// ---------------------------------------------------------------------------

/// Manages on-demand loading and unloading of fractal subgraphs.
///
/// The loader is the bridge between the hierarchical DAG structure
/// (super-nodes and subgraphs) and the memory manager. When the
/// scheduler needs to execute a node, it asks the loader to ensure
/// the node's subgraph is in RAM.
pub struct FractalLoader {
    /// Currently loaded subgraphs.
    loaded: HashMap<SubGraphId, SubGraphEntry>,
}

impl FractalLoader {
    /// Creates a new empty loader.
    pub fn new() -> Self {
        Self {
            loaded: HashMap::new(),
        }
    }

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
    ///
    /// This registers all of the subgraph's nodes in the memory manager.
    /// If any node cannot be loaded (memory budget exceeded), the entire
    /// load is rolled back.
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
                last_accessed: Instant::now(),
            },
        );

        Ok(())
    }

    /// Unloads a subgraph from RAM.
    ///
    /// All nodes belonging to the subgraph are evicted from the memory
    /// manager. Returns the total memory freed.
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
    ///
    /// Returns the total memory freed.
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
            entry.last_accessed = Instant::now();
        }
    }
}

impl Default for FractalLoader {
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
    use zenic_graph::{SubGraphDescriptor, SuperNodeDescriptor};
    use zenic_proto::{BusinessDomain, NodeCategory, NodeCriticality, NodeId};

    fn setup_catalog() -> (NodeCatalog, SuperNodeId, SubGraphId, Vec<NodeId>) {
        let mut catalog = NodeCatalog::new();

        // Create super-node.
        let sn_id = SuperNodeId::new();
        catalog
            .register_super_node(SuperNodeDescriptor {
                id: sn_id,
                name: "COMMERCE".to_string(),
                domain: BusinessDomain::ECommerce,
                description: "Test".to_string(),
                sub_graph_ids: vec![],
                criticality: NodeCriticality::High,
                load_policy: LoadPolicy::OnDemand,
                memory_estimate_bytes: 4096,
                max_active_subgraphs: 0,
            })
            .expect("register sn");

        // Create nodes.
        let n1 = NodeId::new();
        let n2 = NodeId::new();
        for (id, name) in [(n1, "inv_check"), (n2, "inv_update")] {
            catalog
                .register_node(zenic_graph::NodeDescriptor {
                    id,
                    name: name.to_string(),
                    version: "1.0.0".to_string(),
                    category: NodeCategory::Decision,
                    domain: BusinessDomain::ECommerce,
                    criticality: NodeCriticality::Medium,
                    load_policy: LoadPolicy::OnDemand,
                    memory_estimate_bytes: 256,
                    dependencies: vec![],
                    super_node_id: Some(sn_id),
                    sub_graph_id: None, // Will be set after we create it.
                    requires_external_api: false,
                    description: format!("Node {}", name),
                })
                .expect("register node");
        }

        // Create sub-graph.
        let sg_id = SubGraphId::new();
        catalog
            .register_sub_graph(SubGraphDescriptor {
                id: sg_id,
                name: "ecommerce_inventory".to_string(),
                domain: BusinessDomain::ECommerce,
                description: "Inventory management".to_string(),
                super_node_id: sn_id,
                node_ids: vec![n1, n2],
                entry_node_ids: vec![n1],
                exit_node_ids: vec![n2],
                load_policy: LoadPolicy::OnDemand,
                criticality: NodeCriticality::Medium,
                memory_estimate_bytes: 512,
                version: "1.0.0".to_string(),
            })
            .expect("register sg");

        (catalog, sn_id, sg_id, vec![n1, n2])
    }

    #[test]
    fn load_sub_graph() {
        let (catalog, _, sg_id, _) = setup_catalog();
        let mut loader = FractalLoader::new();
        let mut mm = MemoryManager::with_limits(20, 102400);

        loader.load_sub_graph(sg_id, &catalog, &mut mm).expect("load");
        assert!(loader.is_loaded(&sg_id));
        assert_eq!(loader.loaded_count(), 1);
        assert_eq!(mm.loaded_node_count(), 2);
    }

    #[test]
    fn load_sub_graph_idempotent() {
        let (catalog, _, sg_id, _) = setup_catalog();
        let mut loader = FractalLoader::new();
        let mut mm = MemoryManager::with_limits(20, 102400);

        loader.load_sub_graph(sg_id, &catalog, &mut mm).expect("load 1");
        loader.load_sub_graph(sg_id, &catalog, &mut mm).expect("load 2");
        assert_eq!(loader.loaded_count(), 1);
    }

    #[test]
    fn unload_sub_graph() {
        let (catalog, _, sg_id, _) = setup_catalog();
        let mut loader = FractalLoader::new();
        let mut mm = MemoryManager::with_limits(20, 102400);

        loader.load_sub_graph(sg_id, &catalog, &mut mm).expect("load");
        let freed = loader.unload_sub_graph(&sg_id, &mut mm).expect("unload");
        assert_eq!(freed, 512);
        assert!(!loader.is_loaded(&sg_id));
        assert_eq!(mm.loaded_node_count(), 0);
    }

    #[test]
    fn unload_not_loaded_is_ok() {
        let mut loader = FractalLoader::new();
        let mut mm = MemoryManager::new();
        let sg_id = SubGraphId::new();
        let freed = loader.unload_sub_graph(&sg_id, &mut mm).expect("unload");
        assert_eq!(freed, 0);
    }

    #[test]
    fn unload_super_node() {
        let (catalog, sn_id, sg_id, _) = setup_catalog();
        let mut loader = FractalLoader::new();
        let mut mm = MemoryManager::with_limits(20, 102400);

        loader.load_sub_graph(sg_id, &catalog, &mut mm).expect("load");
        let freed = loader.unload_super_node(&sn_id, &mut mm);
        assert_eq!(freed, 512);
        assert!(!loader.is_loaded(&sg_id));
    }

    #[test]
    fn find_lru_sub_graph() {
        let (catalog, _, sg_id, _) = setup_catalog();
        let mut loader = FractalLoader::new();
        let mut mm = MemoryManager::with_limits(20, 102400);

        assert!(loader.find_lru_sub_graph().is_none());
        loader.load_sub_graph(sg_id, &catalog, &mut mm).expect("load");
        assert_eq!(loader.find_lru_sub_graph(), Some(sg_id));
    }

    #[test]
    fn loaded_by_super_node() {
        let (catalog, sn_id, sg_id, _) = setup_catalog();
        let mut loader = FractalLoader::new();
        let mut mm = MemoryManager::with_limits(20, 102400);

        loader.load_sub_graph(sg_id, &catalog, &mut mm).expect("load");
        let found = loader.loaded_by_super_node(&sn_id);
        assert_eq!(found.len(), 1);
        assert_eq!(found[0], sg_id);
    }

    #[test]
    fn touch_updates_lru() {
        let (catalog, _, sg_id, _) = setup_catalog();
        let mut loader = FractalLoader::new();
        let mut mm = MemoryManager::with_limits(20, 102400);

        loader.load_sub_graph(sg_id, &catalog, &mut mm).expect("load");
        loader.touch(&sg_id);
        // No assertion on time, just that it doesn't panic.
    }

    #[test]
    fn default_is_new() {
        let loader = FractalLoader::default();
        assert_eq!(loader.loaded_count(), 0);
    }
}
