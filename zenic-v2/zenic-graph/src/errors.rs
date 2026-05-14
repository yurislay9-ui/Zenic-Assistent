//! Error types for the graph layer.

use thiserror::Error;
use zenic_proto::NodeId;

/// Errors that can occur in the graph layer.
#[derive(Debug, Error)]
pub enum GraphError {
    /// The proposed edge would create a cycle in the DAG.
    #[error("cycle detected: adding edge from {from} to {to} would create a cycle")]
    CycleDetected {
        from: NodeId,
        to: NodeId,
    },

    /// A referenced node was not found in the graph.
    #[error("node not found: {0}")]
    NodeNotFound(NodeId),

    /// A referenced super-node was not found in the catalog.
    #[error("super-node not found: {0}")]
    SuperNodeNotFound(String),

    /// A referenced sub-graph was not found.
    #[error("sub-graph not found: {0}")]
    SubGraphNotFound(String),

    /// The edge references a node that does not exist.
    #[error("invalid edge: {message}")]
    InvalidEdge {
        message: String,
    },

    /// A duplicate registration was attempted.
    #[error("duplicate registration: {entity} with key {key}")]
    DuplicateRegistration {
        entity: String,
        key: String,
    },

    /// The graph is empty and has no nodes.
    #[error("empty graph: {0}")]
    EmptyGraph(String),

    /// A catalog operation failed.
    #[error("catalog error: {0}")]
    CatalogError(String),

    /// Validation of the graph structure failed.
    #[error("validation error: {0}")]
    Validation(String),
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use zenic_proto::NodeId;

    #[test]
    fn cycle_detected_display() {
        let from = NodeId::new();
        let to = NodeId::new();
        let err = GraphError::CycleDetected { from, to };
        let msg = err.to_string();
        assert!(msg.contains("cycle detected"));
    }

    #[test]
    fn node_not_found_display() {
        let id = NodeId::new();
        let err = GraphError::NodeNotFound(id);
        let msg = err.to_string();
        assert!(msg.contains("node not found"));
    }

    #[test]
    fn duplicate_registration_display() {
        let err = GraphError::DuplicateRegistration {
            entity: "SuperNode".to_string(),
            key: "COMMERCE".to_string(),
        };
        let msg = err.to_string();
        assert!(msg.contains("COMMERCE"));
        assert!(msg.contains("SuperNode"));
    }
}
