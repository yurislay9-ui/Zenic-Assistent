//! Unit tests for the memory module.

#[cfg(test)]
mod tests {
    use super::*;
    use zenic_proto::{LoadPolicy, NodeId, SubGraphId};

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
        mm.load_node(NodeId::new(), 50, None, LoadPolicy::OnDemand).expect("load 1");
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
        assert_eq!(candidate, Some(first));
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
