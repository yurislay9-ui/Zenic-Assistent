//! # zenic-bench
//!
//! Benchmarks for Zenic-Agents core components.
//!
//! Run all benchmarks:
//! ```sh
//! cargo bench -p zenic-bench
//! ```
//!
//! Run specific benchmark:
//! ```sh
//! cargo bench -p zenic-bench -- memory_cache
//! ```

/// Benchmark suite version
pub const BENCH_VERSION: &str = env!("CARGO_PKG_VERSION");
