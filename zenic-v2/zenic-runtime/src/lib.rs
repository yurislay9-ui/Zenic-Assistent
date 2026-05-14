//! # zenic-runtime
//!
//! Execution runtime, scheduler, and memory manager for Zenic-Agents.
//!
//! This crate provides:
//! - [`ExecutionContext`] / [`NodeInput`] / [`NodeOutput`] — data flowing through the DAG
//! - [`ExecutionResult`] / [`NodeResult`] — outcomes of DAG and node execution
//! - [`MemoryManager`] — RAM budget enforcement (15-25 nodes max)
//! - [`NodeExecutor`] / [`NodeExecutorRegistry`] — trait + registry for node logic
//! - [`DagScheduler`] — topological-order execution with memory awareness
//! - [`FractalLoader`] — on-demand subgraph loading/unloading

pub mod context;
pub mod errors;
pub mod executor;
pub mod loader;
pub mod memory;
pub mod result;
pub mod scheduler;

// Convenience re-exports.
pub use context::{ExecutionContext, NodeInput, NodeOutput};
pub use errors::RuntimeError;
pub use executor::{NoOpExecutor, NodeExecutor, NodeExecutorRegistry, PassThroughExecutor};
pub use loader::{FractalLoader, SubGraphLoadState};
pub use memory::{
    MemoryManager, NodeLoadState, DEFAULT_MAX_LOADED_NODES, DEFAULT_MEMORY_BUDGET_BYTES,
};
pub use result::{ExecutionResult, ExecutionStatus, NodeResult};
pub use scheduler::DagScheduler;
