//! # zenic-graph
//!
//! Fractal DAG graph primitives, catalog, and acyclic validation for Zenic-Agents.
//!
//! This crate provides:
//! - [`NodeDescriptor`] and [`EdgeDescriptor`] — node/edge metadata
//! - [`SuperNodeDescriptor`] — top-level domain grouping (supernodo)
//! - [`SubGraphDescriptor`] — certified sub-DAG (subgrafo)
//! - [`NodeCatalog`] — in-memory registry of all descriptors
//! - [`DirectedAcyclicGraph`] — DAG with cycle detection on edge insertion

pub mod catalog;
pub mod descriptor;
pub mod errors;
pub mod graph;
pub mod subgraph;
pub mod supernode;

// Convenience re-exports.
pub use catalog::NodeCatalog;
pub use descriptor::{EdgeDescriptor, EdgeKind, NodeDescriptor};
pub use errors::GraphError;
pub use graph::DirectedAcyclicGraph;
pub use subgraph::{SubGraphDescriptor, MAX_NODES_PER_SUBGRAPH};
pub use supernode::{SuperNodeDescriptor, MAX_SUBGRAPHS_PER_SUPERNODE};
