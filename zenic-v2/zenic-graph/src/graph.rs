//! Directed Acyclic Graph (DAG) with cycle detection.
//!
//! This is the core graph data structure for Zenic-Agents. It wraps
//! [`petgraph::DiGraph`] and enforces acyclicity on every edge insertion.

use petgraph::algo::{is_cyclic_directed, toposort};
use petgraph::graph::{DiGraph, NodeIndex};
use petgraph::visit::EdgeRef;
use std::collections::HashMap;
use zenic_proto::NodeId;

use crate::descriptor::EdgeDescriptor;
use crate::errors::GraphError;

// ---------------------------------------------------------------------------
// DirectedAcyclicGraph
// ---------------------------------------------------------------------------

/// A directed acyclic graph that enforces acyclicity at insertion time.
///
/// Each node in the graph is identified by a [`NodeId`] and stores a
/// reference to its [`NodeDescriptor`] (via the catalog). Edges are
/// [`EdgeDescriptor`] records.
pub struct DirectedAcyclicGraph {
    /// The underlying petgraph.
    inner: DiGraph<NodeId, EdgeDescriptor>,
    /// Mapping from NodeId to petgraph NodeIndex.
    node_index_map: HashMap<NodeId, NodeIndex>,
    /// Whether the graph has been modified since the last validation.
    dirty: bool,
}

impl DirectedAcyclicGraph {
    /// Creates an empty DAG.
    pub fn new() -> Self {
        Self {
            inner: DiGraph::new(),
            node_index_map: HashMap::new(),
            dirty: false,
        }
    }

    /// Adds a node to the graph.
    ///
    /// Returns the [`NodeId`] for the added node, or an error if a node
    /// with the same ID already exists.
    pub fn add_node(&mut self, node_id: NodeId) -> Result<NodeId, GraphError> {
        if self.node_index_map.contains_key(&node_id) {
            return Err(GraphError::DuplicateRegistration {
                entity: "GraphNode".to_string(),
                key: node_id.to_string(),
            });
        }
        let idx = self.inner.add_node(node_id);
        self.node_index_map.insert(node_id, idx);
        self.dirty = true;
        Ok(node_id)
    }

    /// Adds a directed edge from `from` to `to`, checking for cycles first.
    ///
    /// If adding the edge would create a cycle, the edge is not added and
    /// a [`GraphError::CycleDetected`] error is returned.
    pub fn add_edge(&mut self, edge: EdgeDescriptor) -> Result<(), GraphError> {
        let from_idx = self
            .node_index_map
            .get(&edge.from)
            .ok_or(GraphError::NodeNotFound(edge.from))?;
        let to_idx = self
            .node_index_map
            .get(&edge.to)
            .ok_or(GraphError::NodeNotFound(edge.to))?;

        // Tentatively add the edge.
        self.inner.add_edge(*from_idx, *to_idx, edge.clone());
        self.dirty = true;

        // Check for cycles.
        if is_cyclic_directed(&self.inner) {
            // Rollback: remove the last edge.
            // petgraph doesn't have a direct "remove last edge" API,
            // so we rebuild without the last edge.
            self.remove_last_edge(*from_idx, *to_idx);
            return Err(GraphError::CycleDetected {
                from: edge.from,
                to: edge.to,
            });
        }

        Ok(())
    }

    /// Returns the topological ordering of the graph, or an error if the
    /// graph contains a cycle (should not happen if edges were added via
    /// `add_edge`, but this is a safety check).
    pub fn topological_sort(&self) -> Result<Vec<NodeId>, GraphError> {
        let sorted = toposort(&self.inner, None).map_err(|cycle| {
            let node_id = self.inner[cycle.node_id()];
            GraphError::Validation(format!(
                "topological sort failed: cycle involves node {}",
                node_id
            ))
        })?;
        Ok(sorted.iter().map(|idx| self.inner[*idx]).collect())
    }

    /// Returns the IDs of all root nodes (nodes with no incoming edges).
    pub fn roots(&self) -> Vec<NodeId> {
        self.inner
            .node_indices()
            .filter(|idx| self.inner.edges_directed(*idx, petgraph::Direction::Incoming).count() == 0)
            .map(|idx| self.inner[idx])
            .collect()
    }

    /// Returns the IDs of all leaf nodes (nodes with no outgoing edges).
    pub fn leaves(&self) -> Vec<NodeId> {
        self.inner
            .node_indices()
            .filter(|idx| self.inner.edges_directed(*idx, petgraph::Direction::Outgoing).count() == 0)
            .map(|idx| self.inner[idx])
            .collect()
    }

    /// Returns the number of nodes in the graph.
    pub fn node_count(&self) -> usize {
        self.inner.node_count()
    }

    /// Returns the number of edges in the graph.
    pub fn edge_count(&self) -> usize {
        self.inner.edge_count()
    }

    /// Returns true if the graph contains the given node.
    pub fn contains_node(&self, id: &NodeId) -> bool {
        self.node_index_map.contains_key(id)
    }

    /// Returns the immediate successors of a node.
    pub fn successors(&self, id: &NodeId) -> Vec<NodeId> {
        self.node_index_map
            .get(id)
            .map(|idx| {
                self.inner
                    .neighbors_directed(*idx, petgraph::Direction::Outgoing)
                    .map(|n| self.inner[n])
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Returns the immediate predecessors of a node.
    pub fn predecessors(&self, id: &NodeId) -> Vec<NodeId> {
        self.node_index_map
            .get(id)
            .map(|idx| {
                self.inner
                    .neighbors_directed(*idx, petgraph::Direction::Incoming)
                    .map(|n| self.inner[n])
                    .collect()
            })
            .unwrap_or_default()
    }

    /// Validates that the graph is acyclic and has at least one root.
    pub fn validate(&self) -> Result<(), GraphError> {
        if self.inner.node_count() == 0 {
            return Err(GraphError::EmptyGraph("graph has no nodes".to_string()));
        }
        if is_cyclic_directed(&self.inner) {
            return Err(GraphError::Validation("graph contains a cycle".to_string()));
        }
        if self.roots().is_empty() {
            return Err(GraphError::Validation(
                "graph has no root nodes".to_string(),
            ));
        }
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------------

    /// Removes the most recently added edge from `from_idx` to `to_idx`.
    ///
    /// This is used for cycle-detection rollback. We find the edge and
    /// remove it by its petgraph edge index.
    fn remove_last_edge(&mut self, from_idx: NodeIndex, to_idx: NodeIndex) {
        // Find the edge to remove (the last one added from -> to).
        let edge_to_remove = self
            .inner
            .edges_connecting(from_idx, to_idx)
            .last()
            .map(|e| e.id());

        if let Some(edge_id) = edge_to_remove {
            self.inner.remove_edge(edge_id);
        }
    }
}

impl Default for DirectedAcyclicGraph {
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
    fn empty_graph_has_no_nodes() {
        let g = DirectedAcyclicGraph::new();
        assert_eq!(g.node_count(), 0);
        assert!(g.validate().is_err()); // Empty graph fails validation
    }

    #[test]
    fn add_node_and_query() {
        let mut g = DirectedAcyclicGraph::new();
        let a = NodeId::new();
        g.add_node(a).expect("add");
        assert_eq!(g.node_count(), 1);
        assert!(g.contains_node(&a));
    }

    #[test]
    fn duplicate_node_fails() {
        let mut g = DirectedAcyclicGraph::new();
        let a = NodeId::new();
        g.add_node(a).expect("add");
        assert!(g.add_node(a).is_err());
    }

    #[test]
    fn add_edge_and_topological_sort() {
        let mut g = DirectedAcyclicGraph::new();
        let a = NodeId::new();
        let b = NodeId::new();
        let c = NodeId::new();
        g.add_node(a).expect("add");
        g.add_node(b).expect("add");
        g.add_node(c).expect("add");

        g.add_edge(EdgeDescriptor::data(a, b)).expect("edge");
        g.add_edge(EdgeDescriptor::data(b, c)).expect("edge");

        let sorted = g.topological_sort().expect("topo");
        assert_eq!(sorted.len(), 3);
        assert_eq!(sorted[0], a);
        assert_eq!(sorted[1], b);
        assert_eq!(sorted[2], c);
    }

    #[test]
    fn cycle_detection_rejects_edge() {
        let mut g = DirectedAcyclicGraph::new();
        let a = NodeId::new();
        let b = NodeId::new();
        let c = NodeId::new();
        g.add_node(a).expect("add");
        g.add_node(b).expect("add");
        g.add_node(c).expect("add");

        g.add_edge(EdgeDescriptor::data(a, b)).expect("edge");
        g.add_edge(EdgeDescriptor::data(b, c)).expect("edge");

        // This would create a cycle: c -> a
        let result = g.add_edge(EdgeDescriptor::data(c, a));
        assert!(result.is_err());
        // Graph should still be acyclic.
        assert!(g.validate().is_ok());
    }

    #[test]
    fn roots_and_leaves() {
        let mut g = DirectedAcyclicGraph::new();
        let a = NodeId::new();
        let b = NodeId::new();
        let c = NodeId::new();
        g.add_node(a).expect("add");
        g.add_node(b).expect("add");
        g.add_node(c).expect("add");

        g.add_edge(EdgeDescriptor::data(a, b)).expect("edge");
        g.add_edge(EdgeDescriptor::data(a, c)).expect("edge");

        let roots = g.roots();
        assert_eq!(roots.len(), 1);
        assert_eq!(roots[0], a);

        let leaves = g.leaves();
        assert_eq!(leaves.len(), 2);
        assert!(leaves.contains(&b));
        assert!(leaves.contains(&c));
    }

    #[test]
    fn successors_and_predecessors() {
        let mut g = DirectedAcyclicGraph::new();
        let a = NodeId::new();
        let b = NodeId::new();
        let c = NodeId::new();
        g.add_node(a).expect("add");
        g.add_node(b).expect("add");
        g.add_node(c).expect("add");

        g.add_edge(EdgeDescriptor::data(a, b)).expect("edge");
        g.add_edge(EdgeDescriptor::data(a, c)).expect("edge");

        let succ_a = g.successors(&a);
        assert_eq!(succ_a.len(), 2);

        let pred_b = g.predecessors(&b);
        assert_eq!(pred_b.len(), 1);
        assert_eq!(pred_b[0], a);
    }

    #[test]
    fn edge_to_nonexistent_node_fails() {
        let mut g = DirectedAcyclicGraph::new();
        let a = NodeId::new();
        let b = NodeId::new(); // Not added
        g.add_node(a).expect("add");

        let result = g.add_edge(EdgeDescriptor::data(a, b));
        assert!(result.is_err());
    }

    #[test]
    fn valid_graph_passes_validation() {
        let mut g = DirectedAcyclicGraph::new();
        let a = NodeId::new();
        let b = NodeId::new();
        g.add_node(a).expect("add");
        g.add_node(b).expect("add");
        g.add_edge(EdgeDescriptor::data(a, b)).expect("edge");
        assert!(g.validate().is_ok());
    }

    #[test]
    fn default_is_empty() {
        let g = DirectedAcyclicGraph::default();
        assert_eq!(g.node_count(), 0);
    }
}
