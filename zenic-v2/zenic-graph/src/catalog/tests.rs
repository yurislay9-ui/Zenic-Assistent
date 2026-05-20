//! Unit tests for the NodeCatalog.

#[cfg(test)]
mod tests {
    use super::*;
    use zenic_proto::NodeCategory;

    fn make_node(name: &str, domain: BusinessDomain) -> NodeDescriptor {
        NodeDescriptor {
            id: NodeId::new(),
            name: name.to_string(),
            version: "1.0.0".to_string(),
            category: NodeCategory::Decision,
            domain,
            criticality: NodeCriticality::High,
            load_policy: LoadPolicy::OnDemand,
            memory_estimate_bytes: 512,
            dependencies: vec![],
            super_node_id: None,
            sub_graph_id: None,
            requires_external_api: false,
            description: format!("Node {}", name),
        }
    }

    fn make_supernode(name: &str, domain: BusinessDomain) -> SuperNodeDescriptor {
        SuperNodeDescriptor {
            id: SuperNodeId::new(),
            name: name.to_string(),
            domain,
            description: format!("Super-node {}", name),
            sub_graph_ids: vec![],
            criticality: NodeCriticality::High,
            load_policy: LoadPolicy::OnDemand,
            memory_estimate_bytes: 4096,
            max_active_subgraphs: 0,
        }
    }

    #[test]
    fn register_and_retrieve_node() {
        let mut catalog = NodeCatalog::new();
        let node = make_node("test", BusinessDomain::ECommerce);
        let id = node.id;
        catalog.register_node(node).expect("register");
        assert_eq!(catalog.node_count(), 1);
        assert!(catalog.get_node(&id).is_some());
    }

    #[test]
    fn duplicate_node_registration_fails() {
        let mut catalog = NodeCatalog::new();
        let node = make_node("test", BusinessDomain::ECommerce);
        let id = node.id;
        catalog.register_node(node).expect("register");
        let duplicate = NodeDescriptor {
            id,
            name: "duplicate".to_string(),
            version: "1.0.0".to_string(),
            category: NodeCategory::Orchestrator,
            domain: BusinessDomain::Retail,
            criticality: NodeCriticality::Critical,
            load_policy: LoadPolicy::Always,
            memory_estimate_bytes: 256,
            dependencies: vec![],
            super_node_id: None,
            sub_graph_id: None,
            requires_external_api: false,
            description: "Duplicate".to_string(),
        };
        assert!(catalog.register_node(duplicate).is_err());
    }

    #[test]
    fn nodes_by_domain() {
        let mut catalog = NodeCatalog::new();
        catalog
            .register_node(make_node("a", BusinessDomain::ECommerce))
            .expect("register");
        catalog
            .register_node(make_node("b", BusinessDomain::Finance))
            .expect("register");
        catalog
            .register_node(make_node("c", BusinessDomain::ECommerce))
            .expect("register");

        let ecommerce = catalog.nodes_by_domain(BusinessDomain::ECommerce);
        assert_eq!(ecommerce.len(), 2);
    }

    #[test]
    fn register_and_retrieve_supernode() {
        let mut catalog = NodeCatalog::new();
        let sn = make_supernode("COMMERCE", BusinessDomain::ECommerce);
        let id = sn.id;
        catalog.register_super_node(sn).expect("register");
        assert_eq!(catalog.super_node_count(), 1);
        assert!(catalog.get_super_node(&id).is_some());
    }

    #[test]
    fn supernode_by_name() {
        let mut catalog = NodeCatalog::new();
        let sn = make_supernode("COMMERCE", BusinessDomain::ECommerce);
        catalog.register_super_node(sn).expect("register");
        let found = catalog.get_super_node_by_name("COMMERCE");
        assert!(found.is_some());
        assert_eq!(found.unwrap().name, "COMMERCE");
    }

    #[test]
    fn supernodes_by_domain() {
        let mut catalog = NodeCatalog::new();
        catalog
            .register_super_node(make_supernode("COMMERCE", BusinessDomain::ECommerce))
            .expect("register");
        catalog
            .register_super_node(make_supernode("FINANCE", BusinessDomain::Finance))
            .expect("register");
        let found = catalog.super_nodes_by_domain(BusinessDomain::ECommerce);
        assert_eq!(found.len(), 1);
    }

    #[test]
    fn always_loaded_memory() {
        let mut catalog = NodeCatalog::new();
        let mut always_node = make_node("always", BusinessDomain::ECommerce);
        always_node.load_policy = LoadPolicy::Always;
        always_node.criticality = NodeCriticality::Critical;
        always_node.memory_estimate_bytes = 1024;
        catalog.register_node(always_node).expect("register");

        let mut on_demand_node = make_node("ondemand", BusinessDomain::ECommerce);
        on_demand_node.memory_estimate_bytes = 2048;
        catalog.register_node(on_demand_node).expect("register");

        assert_eq!(catalog.always_loaded_memory(), 1024);
        assert_eq!(catalog.total_memory(), 3072);
    }

    #[test]
    fn empty_catalog_validates() {
        let catalog = NodeCatalog::new();
        assert!(catalog.validate().is_ok());
    }

    #[test]
    fn catalog_default_is_new() {
        let catalog = NodeCatalog::default();
        assert_eq!(catalog.node_count(), 0);
    }
}
