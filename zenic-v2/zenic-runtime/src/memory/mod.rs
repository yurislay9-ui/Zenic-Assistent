//! Memory manager for the fractal DAG runtime.
//!
//! Enforces the RAM budget constraint: only a configurable number of nodes
//! (default 25) may be resident in memory at once.

mod types;
mod manager;
mod tests;

pub use types::{NodeLoadState, DEFAULT_MAX_LOADED_NODES, DEFAULT_MEMORY_BUDGET_BYTES};
pub use types::MemoryManager;
