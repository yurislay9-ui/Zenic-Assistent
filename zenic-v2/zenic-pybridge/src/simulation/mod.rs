//! Dry-run Simulation Engine — Rust DAG extension for Zenic-Agents.
//!
//! This module implements the C1 core in Rust for:
//! - DAG node dependency resolution and topological sorting
//! - Dry-run execution simulation without side effects
//! - Impact score aggregation across DAG paths
//! - Cycle detection in DAG definitions
//! - Parallel-safe node state tracking
//!
//! Rust is ideal for this because:
//! - The 59-node DAG needs fast topological sort on every dry-run
//! - Graph operations are naturally suited to Rust's ownership model
//! - Cycle detection requires careful pointer management
//! - Impact aggregation is compute-intensive with many nodes

pub mod runner;
pub mod types;
pub mod validator;

// Re-export all public PyO3 functions so lib.rs can reference simulation::*
pub use runner::{topological_sort, simulate_dag};
pub use validator::{detect_cycles, aggregate_impact};
