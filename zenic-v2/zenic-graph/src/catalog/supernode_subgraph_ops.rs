//! NodeCatalog super-node and sub-graph operations, memory estimation, and validation.

use zenic_proto::{BusinessDomain, LoadPolicy, SubGraphId, SuperNodeId};

use crate::errors::GraphError;
use crate::subgraph::SubGraphDescriptor;
use crate::supernode::SuperNodeDescriptor;

use super::struct_def::NodeCatalog;

impl NodeCatalog {
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
