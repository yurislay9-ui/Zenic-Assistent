//! NodeCatalog node operations: register, get, query by domain/criticality/load_policy.

use zenic_proto::{BusinessDomain, LoadPolicy, NodeCriticality, NodeId};

use crate::descriptor::NodeDescriptor;
use crate::errors::GraphError;

use super::struct_def::NodeCatalog;

impl NodeCatalog {
    /// Registers a node descriptor.
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
}
