//! Risk Prediction & Blast Radius Calculator — Graph analysis for Zenic-Agents.
//!
//! This module implements the F3 core in Rust for:
//! - Blast radius calculation: How many nodes are affected if a node fails
//! - Dependency graph analysis: Downstream impact propagation
//! - Risk propagation: How risk scores cascade through the DAG
//! - Critical path identification: Which nodes are on the critical path
//! - Reachability analysis: Which nodes can be reached from a given node
//!
//! Rust is ideal for this because:
//! - Graph traversal is computationally expensive with 59 nodes
//! - BFS/DFS on large graphs benefits from zero-cost abstractions
//! - Parallel risk propagation requires safe concurrent access
//! - Memory layout matters for cache-efficient graph algorithms

pub mod assessor;
pub mod calculator;
pub mod types;

// Re-export all public API so that `risk::calculate_blast_radius` etc.
// continue to work without changes in the parent lib.rs.
pub use calculator::calculate_blast_radius;
pub use calculator::multi_node_blast_radius;
pub use assessor::compute_reachability;
pub use assessor::find_critical_path;
pub use assessor::propagate_risks;
