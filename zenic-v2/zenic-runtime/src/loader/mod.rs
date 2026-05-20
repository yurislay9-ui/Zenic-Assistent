//! Fractal loader for on-demand subgraph loading/unloading.
//!
//! The [`FractalLoader`] manages which subgraphs are loaded into RAM.
//! It cooperates with the [`MemoryManager`](super::memory::MemoryManager)
//! to enforce memory budgets and evicts idle subgraphs using LRU policy.

mod types;
mod operations;
mod tests;

pub use types::{FractalLoader, SubGraphLoadState};
