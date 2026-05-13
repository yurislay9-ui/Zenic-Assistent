//! Zenic-Agents Native Extension Module
//!
//! This is the main entry point for the `_zenic_native` Python extension
//! module built with PyO3. It exposes high-performance cryptographic,
//! hashing, database, forensic, rollback, event-bus, simulation,
//! and risk-prediction operations implemented in Rust.
//!
//! # Modules
//!
//! - `crypto`: Key derivation (PBKDF2, Argon2id) and constant-time comparison
//! - `hash`: Fast native hashing (BLAKE3, xxHash64, Merkle root)
//! - `db`: SQLCipher integration via rusqlite
//! - `forensic`: Merkle chain verification, hash generation, integrity validation (A1)
//! - `rollback`: Atomic cross-resource rollback, file snapshot/restore (A3)
//! - `eventbus`: High-speed event dispatch, wildcard matching, dedup (B1)
//! - `simulation`: DAG topological sort, dry-run simulation, impact aggregation (C1)
//! - `risk`: Blast radius calculation, risk propagation, critical path (F3)
//! - `bus`: Shared memory bus, shared state, ring buffer (inter-agent communication)
//! - `license`: Licensing, anti-tampering, hardware binding, kill switch (Phase 6.3)

mod bus;
mod crypto;
mod db;
mod eventbus;
mod forensic;
mod hash;
mod license;
mod risk;
mod rollback;
mod safety_gate;
mod simulation;

use pyo3::prelude::*;

/// Register the `_zenic_native` Python module.
///
/// This function is called by the Python interpreter when the extension
/// module is imported. All sub-module functions are registered here.
#[pymodule]
fn _zenic_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Crypto functions
    m.add_function(wrap_pyfunction!(crypto::pbkdf2_derive_key, m)?)?;
    m.add_function(wrap_pyfunction!(crypto::argon2id_hash, m)?)?;
    m.add_function(wrap_pyfunction!(crypto::constant_time_compare, m)?)?;

    // Hash functions
    m.add_function(wrap_pyfunction!(hash::blake3_hash, m)?)?;
    m.add_function(wrap_pyfunction!(hash::xxhash64, m)?)?;
    m.add_function(wrap_pyfunction!(hash::merkle_root, m)?)?;

    // Database functions
    m.add_class::<db::EncryptedDb>()?;

    // Forensic Audit (A1) — Merkle chain verification, integrity
    m.add_function(wrap_pyfunction!(forensic::forensic_hash, m)?)?;
    m.add_function(wrap_pyfunction!(forensic::chain_hash, m)?)?;
    m.add_function(wrap_pyfunction!(forensic::verify_merkle_chain, m)?)?;
    m.add_function(wrap_pyfunction!(forensic::merkle_proof, m)?)?;
    m.add_function(wrap_pyfunction!(forensic::batch_verify_chains, m)?)?;

    // Coordinated Rollback (A3) — Atomic cross-resource
    m.add_function(wrap_pyfunction!(rollback::snapshot_file, m)?)?;
    m.add_function(wrap_pyfunction!(rollback::restore_file, m)?)?;
    m.add_function(wrap_pyfunction!(rollback::verify_rollback_readiness, m)?)?;
    m.add_function(wrap_pyfunction!(rollback::file_hash, m)?)?;
    m.add_class::<rollback::RollbackActionStatus>()?;
    m.add_class::<rollback::RollbackResourceType>()?;

    // High-Speed Event Bus (B1) — Low-latency dispatch
    m.add_function(wrap_pyfunction!(eventbus::wildcard_match, m)?)?;
    m.add_function(wrap_pyfunction!(eventbus::resolve_routes, m)?)?;
    m.add_function(wrap_pyfunction!(eventbus::batch_resolve_routes, m)?)?;
    m.add_function(wrap_pyfunction!(eventbus::deduplicate_events, m)?)?;
    m.add_function(wrap_pyfunction!(eventbus::sort_by_priority, m)?)?;
    m.add_class::<eventbus::EventPriority>()?;

    // Dry-run Simulation (C1) — DAG extension
    m.add_function(wrap_pyfunction!(simulation::topological_sort, m)?)?;
    m.add_function(wrap_pyfunction!(simulation::detect_cycles, m)?)?;
    m.add_function(wrap_pyfunction!(simulation::aggregate_impact, m)?)?;
    m.add_function(wrap_pyfunction!(simulation::simulate_dag, m)?)?;

    // Risk Prediction (F3) — Blast radius, propagation
    m.add_function(wrap_pyfunction!(risk::calculate_blast_radius, m)?)?;
    m.add_function(wrap_pyfunction!(risk::propagate_risks, m)?)?;
    m.add_function(wrap_pyfunction!(risk::find_critical_path, m)?)?;
    m.add_function(wrap_pyfunction!(risk::compute_reachability, m)?)?;
    m.add_function(wrap_pyfunction!(risk::multi_node_blast_radius, m)?)?;


    // Shared Memory Bus — High-speed inter-agent communication
    m.add_class::<bus::SharedMemoryBus>()?;
    m.add_class::<bus::SharedState>()?;
    m.add_class::<bus::RingBuffer>()?;

    // Safety Gate — Deterministic safety validation engine
    m.add_class::<safety_gate::ActionCategory>()?;
    m.add_class::<safety_gate::SafetyVerdict>()?;
    m.add_class::<safety_gate::SafetyCheckResult>()?;
    m.add_function(wrap_pyfunction!(safety_gate::safety_validate, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate::classify_action, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate::check_rate_limit, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate::confirm_action, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate::approve_action, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate::is_confirmed, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate::is_approved, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate::reset_safety_gate, m)?)?;

    // Licensing & Anti-tampering — Security-critical license operations
    m.add_class::<license::LicenseTier>()?;
    m.add_class::<license::LicenseStatus>()?;
    m.add_class::<license::LicenseInfo>()?;
    m.add_function(wrap_pyfunction!(license::verify_license, m)?)?;
    m.add_function(wrap_pyfunction!(license::generate_hardware_fingerprint, m)?)?;
    m.add_function(wrap_pyfunction!(license::verify_hardware_binding, m)?)?;
    m.add_function(wrap_pyfunction!(license::check_tampering, m)?)?;
    m.add_function(wrap_pyfunction!(license::sign_data, m)?)?;
    m.add_function(wrap_pyfunction!(license::verify_signature, m)?)?;
    m.add_function(wrap_pyfunction!(license::check_kill_switch, m)?)?;

    // Module metadata
    m.add("__version__", "2.0.0")?;

    Ok(())
}
