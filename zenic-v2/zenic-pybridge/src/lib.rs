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
//! - `niche`: Core niche types — NicheDefinition, NicheCategory, TemplateFieldSchema (Phase 6.A)
//! - `catalog`: Static compiled catalog of 24 cutting-edge niches (Phase 6.A)
//! - `template`: YAML template generation, validation, missing fields (Phase 6.A)
//! - `ingest`: Document ingestion — format detection, text extraction, key-value parsing (Phase 6.B)
//! - `extractor`: Field extraction — pattern matching, confidence scoring, template auto-fill (Phase 6.B)
//! - `completer`: Template Completion Agent — interactive Q&A, validation, finalization (Phase 6.C)
//! - `certifier`: Blueprint Certification — template → CertifiedBlueprint, ECDSA signing, Phase 5 bridge (Phase 6.D)
//! - `safety_gate_extended`: Domain-specific safety rules + compliance per NicheCategory (Phase D)
//! - `e2e_pipeline`: Complete E2E niche onboarding pipeline (Phase D)

mod bus;
mod catalog;
mod certifier;
mod completer;
mod crypto;
mod db;
mod e2e_pipeline;
mod eventbus;
mod extractor;
mod forensic;
mod hash;
mod ingest;
mod license;
mod memory_chip;
mod niche;
mod risk;
mod rollback;
mod safety_gate;
mod safety_gate_extended;
mod simulation;
mod template;

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

    // Niche Core Types (Phase 6.A) — Rust-compiled niche definitions
    m.add_class::<niche::NicheCategory>()?;
    m.add_class::<niche::DataSensitivity>()?;
    m.add_class::<niche::FieldRequirement>()?;
    m.add_class::<niche::TemplateFieldType>()?;
    m.add_class::<niche::TemplateFieldSchema>()?;
    m.add_class::<niche::TemplateSection>()?;
    m.add_class::<niche::NicheDefinition>()?;
    m.add_function(wrap_pyfunction!(niche::get_niche_categories, m)?)?;
    m.add_function(wrap_pyfunction!(niche::get_niche_category_display_names, m)?)?;

    // Niche Catalog (Phase 6.A) — Static compiled catalog of 24 niches
    m.add_function(wrap_pyfunction!(catalog::catalog_get_all, m)?)?;
    m.add_function(wrap_pyfunction!(catalog::catalog_get_by_id, m)?)?;
    m.add_function(wrap_pyfunction!(catalog::catalog_get_by_category, m)?)?;
    m.add_function(wrap_pyfunction!(catalog::catalog_search, m)?)?;
    m.add_function(wrap_pyfunction!(catalog::catalog_count, m)?)?;
    m.add_function(wrap_pyfunction!(catalog::catalog_ids, m)?)?;

    // YAML Template System (Phase 6.A) — Generation, validation, fill
    m.add_function(wrap_pyfunction!(template::template_generate, m)?)?;
    m.add_function(wrap_pyfunction!(template::template_generate_from_niche, m)?)?;
    m.add_function(wrap_pyfunction!(template::template_validate, m)?)?;
    m.add_function(wrap_pyfunction!(template::template_missing_fields, m)?)?;
    m.add_function(wrap_pyfunction!(template::template_set_field, m)?)?;
    m.add_function(wrap_pyfunction!(template::template_to_yaml, m)?)?;

    // Document Ingestion (Phase 6.B) — Format detection, text extraction
    m.add_class::<ingest::DocumentFormat>()?;
    m.add_class::<ingest::ExtractedText>()?;
    m.add_class::<ingest::BatchExtractionResult>()?;
    m.add_function(wrap_pyfunction!(ingest::ingest_detect_format, m)?)?;
    m.add_function(wrap_pyfunction!(ingest::ingest_extract_text_simple, m)?)?;
    m.add_function(wrap_pyfunction!(ingest::ingest_process_extracted_text, m)?)?;
    m.add_function(wrap_pyfunction!(ingest::ingest_extract_text_batch, m)?)?;
    m.add_function(wrap_pyfunction!(ingest::ingest_supported_formats, m)?)?;
    m.add_function(wrap_pyfunction!(ingest::ingest_validate_size, m)?)?;
    m.add_function(wrap_pyfunction!(ingest::ingest_combine_texts, m)?)?;
    m.add_function(wrap_pyfunction!(ingest::ingest_extract_key_value_pairs, m)?)?;

    // Field Extraction (Phase 6.B) — Pattern matching, confidence, auto-fill
    m.add_class::<extractor::FieldMatch>()?;
    m.add_class::<extractor::ExtractionResult>()?;
    m.add_function(wrap_pyfunction!(extractor::extractor_match_fields, m)?)?;
    m.add_function(wrap_pyfunction!(extractor::extractor_apply_matches, m)?)?;
    m.add_function(wrap_pyfunction!(extractor::extractor_confidence_score, m)?)?;
    m.add_function(wrap_pyfunction!(extractor::extractor_find_candidates, m)?)?;
    m.add_function(wrap_pyfunction!(extractor::extractor_stats, m)?)?;

    // Template Completion Agent (Phase 6.C) — Interactive Q&A, validation, finalization
    m.add_class::<completer::CompletionSession>()?;
    m.add_class::<completer::CompletionQuestion>()?;
    m.add_class::<completer::CompletionRound>()?;
    m.add_class::<completer::CompletionResult>()?;
    m.add_function(wrap_pyfunction!(completer::completer_start_session, m)?)?;
    m.add_function(wrap_pyfunction!(completer::completer_ingest_documents, m)?)?;
    m.add_function(wrap_pyfunction!(completer::completer_get_questions, m)?)?;
    m.add_function(wrap_pyfunction!(completer::completer_submit_answer, m)?)?;
    m.add_function(wrap_pyfunction!(completer::completer_submit_answers, m)?)?;
    m.add_function(wrap_pyfunction!(completer::completer_validate_answer, m)?)?;
    m.add_function(wrap_pyfunction!(completer::completer_get_progress, m)?)?;
    m.add_function(wrap_pyfunction!(completer::completer_is_complete, m)?)?;
    m.add_function(wrap_pyfunction!(completer::completer_finalize, m)?)?;
    m.add_function(wrap_pyfunction!(completer::completer_get_field_suggestions, m)?)?;

    // Blueprint Certification (Phase 6.D) — Template → CertifiedBlueprint, ECDSA signing
    m.add_class::<certifier::CertificationStatus>()?;
    m.add_class::<certifier::BlueprintConfig>()?;
    m.add_class::<certifier::DbTableDef>()?;
    m.add_class::<certifier::ColumnDef>()?;
    m.add_class::<certifier::MonitorDef>()?;
    m.add_class::<certifier::ActionDef>()?;
    m.add_class::<certifier::CertifiedBlueprint>()?;
    m.add_class::<certifier::CertificationResult>()?;
    m.add_function(wrap_pyfunction!(certifier::certifier_from_template, m)?)?;
    m.add_function(wrap_pyfunction!(certifier::certifier_sign, m)?)?;
    m.add_function(wrap_pyfunction!(certifier::certifier_verify, m)?)?;
    m.add_function(wrap_pyfunction!(certifier::certifier_compute_hash, m)?)?;
    m.add_function(wrap_pyfunction!(certifier::certifier_validate_config, m)?)?;
    m.add_function(wrap_pyfunction!(certifier::certifier_to_blueprint_dict, m)?)?;
    m.add_function(wrap_pyfunction!(certifier::certifier_export_yaml, m)?)?;

    // Safety Gate Extended (Phase D) — Domain-specific safety rules + compliance
    m.add_class::<safety_gate_extended::ComplianceStandard>()?;
    m.add_class::<safety_gate_extended::DomainSafetyRule>()?;
    m.add_class::<safety_gate_extended::ComplianceCheckResult>()?;
    m.add_class::<safety_gate_extended::DomainSafetyCheckResult>()?;
    m.add_function(wrap_pyfunction!(safety_gate_extended::safety_validate_extended, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate_extended::safety_validate_domain, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate_extended::safety_check_compliance, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate_extended::safety_check_compliance_batch, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate_extended::safety_get_domain_rules, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate_extended::safety_escalate_verdict, m)?)?;
    m.add_function(wrap_pyfunction!(safety_gate_extended::safety_get_compliance_for_category, m)?)?;

    // E2E Pipeline (Phase D) — Complete niche onboarding pipeline
    m.add_class::<e2e_pipeline::E2EPipelineStep>()?;
    m.add_class::<e2e_pipeline::E2EPipelineState>()?;
    m.add_class::<e2e_pipeline::E2EPipelineResult>()?;
    m.add_function(wrap_pyfunction!(e2e_pipeline::e2e_start, m)?)?;
    m.add_function(wrap_pyfunction!(e2e_pipeline::e2e_upload_documents, m)?)?;
    m.add_function(wrap_pyfunction!(e2e_pipeline::e2e_get_questions, m)?)?;
    m.add_function(wrap_pyfunction!(e2e_pipeline::e2e_submit_answer, m)?)?;
    m.add_function(wrap_pyfunction!(e2e_pipeline::e2e_submit_answers, m)?)?;
    m.add_function(wrap_pyfunction!(e2e_pipeline::e2e_validate, m)?)?;
    m.add_function(wrap_pyfunction!(e2e_pipeline::e2e_safety_check, m)?)?;
    m.add_function(wrap_pyfunction!(e2e_pipeline::e2e_certify, m)?)?;
    m.add_function(wrap_pyfunction!(e2e_pipeline::e2e_export, m)?)?;
    m.add_function(wrap_pyfunction!(e2e_pipeline::e2e_get_progress, m)?)?;

    // Memory Chip (Phase 3/4) — Adaptive Binary Memory Chip PyO3 bridge + TheoremCache
    m.add_class::<memory_chip::MemoryChip>()?;
    m.add_function(wrap_pyfunction!(memory_chip::theorem_cache_serialize, m)?)?;
    m.add_function(wrap_pyfunction!(memory_chip::theorem_cache_deserialize, m)?)?;

    // Module metadata
    m.add("__version__", "2.5.0")?;

    Ok(())
}
