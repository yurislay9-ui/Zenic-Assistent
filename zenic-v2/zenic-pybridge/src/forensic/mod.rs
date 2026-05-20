//! Forensic Audit Engine — Merkle chain verification, hash generation,
//! and integrity validation for Zenic-Agents.
//!
//! This module implements the core security layer (A1) in Rust for:
//! - BLAKE3 hash generation for audit entries
//! - Merkle chain construction and verification
//! - Chain integrity validation with detailed break reporting
//! - Merkle proof generation for individual entries
//! - Atomic batch verification for high-throughput scenarios
//!
//! All operations are designed to be immutable and deterministic:
//! the same input always produces the same output.

pub mod analyzer;
pub mod reporter;
pub mod types;

// Re-export all public PyO3 functions so lib.rs can reference forensic::*
pub use analyzer::{forensic_hash, chain_hash};
pub use reporter::{verify_merkle_chain, merkle_proof, batch_verify_chains};
