//! Coordinated Rollback Engine — Atomic cross-resource rollback for Zenic-Agents.
//!
//! This module implements the A3 core in Rust for:
//! - Atomic state tracking with file-handle-level safety
//! - Cross-resource compensation ordering (reverse execution)
//! - File snapshot/restore with checksums
//! - State machine for rollback lifecycle (IN_PROGRESS → COMMITTED / ROLLED_BACK)
//! - Batch atomic verification (all-or-nothing rollback guarantee)
//!
//! Rust is ideal for this because:
//! - File handles and state pointers are managed safely
//! - Atomic operations are guaranteed by the borrow checker
//! - No GC pauses during critical rollback sequences

mod types;
mod operations;
mod tests;

pub use types::{RollbackActionStatus, RollbackResourceType};
pub use operations::{snapshot_file, restore_file, verify_rollback_readiness, file_hash};
