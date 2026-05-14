//! Node catalog for the fractal DAG.
//!
//! The catalog is an in-memory registry of all node, super-node, and sub-graph
//! descriptors. It provides efficient lookups by ID, domain, criticality, etc.
//! The catalog is populated at startup from the compiled-in definitions
//! (no YAML templates).

use indexmap::IndexMap;
use zenic_proto::{
    BusinessDomain, LoadPolicy, NodeCriticality, NodeId, SubGraphId, SuperNodeId,
};

use crate::descriptor::NodeDescriptor;
use crate::errors::GraphError;
use crate::subgraph::SubGraphDescriptor;
use crate::supernode::SuperNodeDescriptor;

// ---------------------------------------------------------------------------
// NodeCatalog
// ---------------------------------------------------------------------------

/// In-memory catalog of all graph descriptors.
///
/// The catalog is the single source of truth for what nodes, super-nodes,
/// and sub-graphs exist in the system. It is built programmatically at
/// startup (no file I/O, no YAML).
pub struct NodeCatalog {
    /// Node descriptors indexed by NodeId (insertion-ordered).
    nodes: IndexMap<NodeId, NodeDescriptor>,
    /// Super-node descriptors indexed by SuperNodeId.
    super_nodes: IndexMap<SuperNodeId, SuperNodeDescriptor>,
    /// Sub-graph descriptors indexed by SubGraphId.
    sub_graphs: IndexMap<SubGraphId, SubGraphDescriptor>,
    /// Quick lookup: domain -> super-node IDs.
    domain_index: IndexMap<BusinessDomain, Vec<SuperNodeId>>,
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

    // -----------------------------------------------------------------------
    // Node operations
    // -----------------------------------------------------------------------

    /// Registers a node descriptor.
    ///
    /// Returns an error if a node with the same ID already exists.
    pub fn register_node(&mut self, descriptor: NodeDescriptor) -> Result<(), GraphError> {
        descriptor
            .validate()
            .map_err(GraphError::CatalogError)?;

        if self.nodes.contains_key(&descriptor.id) {
            return Err(GraphError::DuplicateRegistration {
                entity: "Node".to_string(),
                key: descriptor.id.to_string(),
            });
        }

        self.nodes.insert(descriptor.id, descriptor);
        Ok(())
    }

    /// Returns a reference to the node descriptor with the given ID.
    pub fn get_node(&self, id: &NodeId) -> Option<&NodeDescriptor> {
        self.nodes.get(id)
    }

    /// Returns an iterator over all registered node descriptors.
    pub fn all_nodes(&self) -> impl Iterator<Item = &NodeDescriptor> {
        self.nodes.values()
    }

    /// Returns the number of registered nodes.
    pub fn node_count(&self) -> usize {
        self.nodes.len()
    }

    /// Returns all nodes matching the given domain.
    pub fn nodes_by_domain(&self, domain: BusinessDomain) -> Vec<&NodeDescriptor> {
        self.nodes
            .values()
            .filter(|n| n.domain == domain)
            .collect()
    }

    /// Returns all nodes matching the given criticality level.
    pub fn nodes_by_criticality(&self, criticality: NodeCriticality) -> Vec<&NodeDescriptor> {
        self.nodes
            .values()
            .filter(|n| n.criticality == criticality)
            .collect()
    }

    /// Returns all nodes with the given load policy.
    pub fn nodes_by_load_policy(&self, policy: LoadPolicy) -> Vec<&NodeDescriptor> {
        self.nodes
            .values()
            .filter(|n| n.load_policy == policy)
            .collect()
    }

    // -----------------------------------------------------------------------
    // Super-node operations
    // -----------------------------------------------------------------------

    /// Registers a super-node descriptor.
    pub fn register_super_node(
        &mut self,
        descriptor: SuperNodeDescriptor,
    ) -> Result<(), GraphError> {
        descriptor
            .validate()
            .map_err(GraphError::CatalogError)?;

        if self.super_nodes.contains_key(&descriptor.id) {
            return Err(GraphError::DuplicateRegistration {
                entity: "SuperNode".to_string(),
                key: descriptor.name.clone(),
            });
        }

        // Update domain index.
        self.domain_index
            .entry(descriptor.domain)
            .or_default()
            .push(descriptor.id);

        self.super_nodes.insert(descriptor.id, descriptor);
        Ok(())
    }

    /// Returns a reference to the super-node descriptor with the given ID.
    pub fn get_super_node(&self, id: &SuperNodeId) -> Option<&SuperNodeDescriptor> {
        self.super_nodes.get(id)
    }

    /// Returns a super-node by its canonical name.
    pub fn get_super_node_by_name(&self, name: &str) -> Option<&SuperNodeDescriptor> {
        self.super_nodes
            .values()
            .find(|sn| sn.name == name)
    }

    /// Returns all super-nodes for the given domain.
    pub fn super_nodes_by_domain(&self, domain: BusinessDomain) -> Vec<&SuperNodeDescriptor> {
        self.domain_index
            .get(&domain)
            .map(|ids| {
                ids.iter()
                    .filter_map(|id| self.super_nodes.get(id))
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Returns an iterator over all registered super-node descriptors.
    pub fn all_super_nodes(&self) -> impl Iterator<Item = &SuperNodeDescriptor> {
        self.super_nodes.values()
    }

    /// Returns the number of registered super-nodes.
    pub fn super_node_count(&self) -> usize {
        self.super_nodes.len()
    }

    // -----------------------------------------------------------------------
    // Sub-graph operations
    // -----------------------------------------------------------------------

    /// Registers a sub-graph descriptor.
    pub fn register_sub_graph(
        &mut self,
        descriptor: SubGraphDescriptor,
    ) -> Result<(), GraphError> {
        descriptor
            .validate()
            .map_err(GraphError::CatalogError)?;

        if self.sub_graphs.contains_key(&descriptor.id) {
            return Err(GraphError::DuplicateRegistration {
                entity: "SubGraph".to_string(),
                key: descriptor.name.clone(),
            });
        }

        // Verify that the parent super-node exists.
        if !self.super_nodes.contains_key(&descriptor.super_node_id) {
            return Err(GraphError::SuperNodeNotFound(descriptor.super_node_id.to_string()));
        }

        self.sub_graphs.insert(descriptor.id, descriptor);
        Ok(())
    }

    /// Returns a reference to the sub-graph descriptor with the given ID.
    pub fn get_sub_graph(&self, id: &SubGraphId) -> Option<&SubGraphDescriptor> {
        self.sub_graphs.get(id)
    }

    /// Returns all sub-graphs belonging to the given super-node.
    pub fn sub_graphs_by_super_node(
        &self,
        super_node_id: &SuperNodeId,
    ) -> Vec<&SubGraphDescriptor> {
        self.sub_graphs
            .values()
            .filter(|sg| &sg.super_node_id == super_node_id)
            .collect()
    }

    /// Returns an iterator over all registered sub-graph descriptors.
    pub fn all_sub_graphs(&self) -> impl Iterator<Item = &SubGraphDescriptor> {
        self.sub_graphs.values()
    }

    /// Returns the number of registered sub-graphs.
    pub fn sub_graph_count(&self) -> usize {
        self.sub_graphs.len()
    }

    // -----------------------------------------------------------------------
    // Memory estimation
    // -----------------------------------------------------------------------

    /// Returns the total estimated memory for all always-loaded nodes.
    pub fn always_loaded_memory(&self) -> u64 {
        self.nodes
            .values()
            .filter(|n| n.load_policy == LoadPolicy::Always)
            .map(|n| n.memory_estimate_bytes)
            .sum()
    }

    /// Returns the total estimated memory for all registered nodes.
    pub fn total_memory(&self) -> u64 {
        self.nodes.values().map(|n| n.memory_estimate_bytes).sum()
    }

    // -----------------------------------------------------------------------
    // Validation
    // -----------------------------------------------------------------------

    /// Validates the entire catalog for cross-reference integrity.
    ///
    /// Checks:
    /// - All node dependencies reference existing nodes.
    /// - All super-node sub_graph_ids reference existing sub-graphs.
    /// - All sub-graph node_ids reference existing nodes.
    pub fn validate(&self) -> Result<(), Vec<GraphError>> {
        let mut errors = Vec::new();

        // Check node dependencies.
        for node in self.nodes.values() {
            for dep_id in &node.dependencies {
                if !self.nodes.contains_key(dep_id) {
                    errors.push(GraphError::NodeNotFound(*dep_id));
                }
            }
        }

        // Check super-node -> sub-graph references.
        for sn in self.super_nodes.values() {
            for sg_id in &sn.sub_graph_ids {
                if !self.sub_graphs.contains_key(sg_id) {
                    errors.push(GraphError::SubGraphNotFound(sg_id.to_string()));
                }
            }
        }

        // Check sub-graph -> node references.
        for sg in self.sub_graphs.values() {
            for node_id in &sg.node_ids {
                if !self.nodes.contains_key(node_id) {
                    errors.push(GraphError::NodeNotFound(*node_id));
                }
            }
        }

        if errors.is_empty() {
            Ok(())
        } else {
            Err(errors)
        }
    }
}

impl Default for NodeCatalog {
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
        // Create a new node with the same ID.
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
