//! Unit tests for the loader module.

#[cfg(test)]
mod tests {
    use super::*;
    use zenic_graph::{SubGraphDescriptor, SuperNodeDescriptor};
    use zenic_proto::{BusinessDomain, NodeCategory, NodeCriticality, NodeId};

    fn setup_catalog() -> (NodeCatalog, SuperNodeId, SubGraphId, Vec<NodeId>) {
        let mut catalog = NodeCatalog::new();

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
                    sub_graph_id: None,
                    requires_external_api: false,
                    description: format!("Node {}", name),
                })
                .expect("register node");
        }

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
    }

    #[test]
    fn default_is_new() {
        let loader = FractalLoader::default();
        assert_eq!(loader.loaded_count(), 0);
    }
}
