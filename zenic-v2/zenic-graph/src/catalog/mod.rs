//! Node catalog for the fractal DAG.
//!
//! The catalog is an in-memory registry of all node, super-node, and sub-graph
//! descriptors.

mod struct_def;
mod node_ops;
mod supernode_subgraph_ops;
mod tests;

pub use struct_def::NodeCatalog;
