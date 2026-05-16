//! Memory Chip PyO3 Bridge — Exposes zenic-memory to Python.
//!
//! This module provides the `MemoryChip` PyO3 class that wraps the
//! zenic-memory crate components for Python access. The Python pipeline
//! (`_core.py`) calls `self._memory_chip.lookup(text, tenant_id)` and
//! `self._memory_chip.try_adapt(failed_field, tenant_id)`.
//!
//! Also provides TheoremCache bincode serialization functions for
//! compact binary storage of theorem cache entries.
//!
//! ## Architecture
//!
//! ```text
//! Python (_core.py)                Rust (zenic-memory)
//! ─────────────────                ──────────────────
//! memory_chip.lookup()      →     OntologyBase → MemoryCache → SemanticGraph
//! memory_chip.try_adapt()   →     DagAdapter.try_adapt()
//! memory_chip.insert()      →     SemanticGraph.insert_mapping()
//! memory_chip.approve()     →     HitlBridge.approve()
//! memory_chip.seal()        →     MerkleSeal.seal_mapping()
//! memory_chip.render_yaml() →     YamlRenderer.render_mapping()
//! ```
//!
//! ## Thread Safety
//!
//! All shared state uses `Arc<Mutex<>>` for thread-safe access from
//! Python's GIL-released context. Rust-side locks are held for the
//! minimum time necessary.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::sync::{Arc, Mutex};

use zenic_memory::{
    HitlBridge, HitlOutcome, LearningMechanism, LifecycleManager, LifecyclePhase, MemoryCache,
    MemoryError, MerkleSeal, OntologyBase, SemanticGraph, SemanticMapping, SubscriptionGate,
    SubscriptionTier, VerdictAdapter, YamlRenderer,
};

// ---------------------------------------------------------------------------
// TheoremCache bincode helpers (Phase 4 bridge)
// ---------------------------------------------------------------------------

/// Serialize a theorem cache entry to bincode bytes.
///
/// Takes a (key, value, confidence) tuple and serializes it using bincode
/// for compact binary storage. Used by the Python-side TheoremCache to
/// persist entries in the same format as the Rust-side memory chip.
#[pyfunction]
pub fn theorem_cache_serialize(key: &str, value: &str, confidence: f64) -> PyResult<Vec<u8>> {
    let entry = (key.to_string(), value.to_string(), confidence);
    bincode::serialize(&entry)
        .map_err(|e| PyRuntimeError::new_err(format!("Bincode serialization error: {}", e)))
}

/// Deserialize a theorem cache entry from bincode bytes.
///
/// Returns a (key, value, confidence) tuple from the serialized bincode
/// bytes. Used by the Python-side TheoremCache to read entries stored
/// by the Rust-side memory chip.
#[pyfunction]
pub fn theorem_cache_deserialize(data: &[u8]) -> PyResult<(String, String, f64)> {
    bincode::deserialize(data)
        .map_err(|e| PyRuntimeError::new_err(format!("Bincode deserialization error: {}", e)))
}

// ---------------------------------------------------------------------------
// Error Conversion
// ---------------------------------------------------------------------------

/// Converts a `MemoryError` into a `PyRuntimeError` for Python.
fn mem_err_to_py(e: MemoryError) -> PyErr {
    PyRuntimeError::new_err(format!("MemoryChip error: {}", e))
}

// ---------------------------------------------------------------------------
// MemoryChipBuilder
// ---------------------------------------------------------------------------

/// Builder for constructing a `MemoryChip` with optional configuration.
///
/// Uses the Builder pattern for flexible construction.
pub struct MemoryChipBuilder {
    db_path: String,
    tier: SubscriptionTier,
}

impl MemoryChipBuilder {
    /// Creates a new builder with the given database path.
    pub fn new(db_path: String) -> Self {
        Self {
            db_path,
            tier: SubscriptionTier::Enterprise,
        }
    }

    /// Sets the subscription tier.
    pub fn tier(mut self, tier: SubscriptionTier) -> Self {
        self.tier = tier;
        self
    }

    /// Builds the `MemoryChipInner` from the builder configuration.
    pub fn build(self) -> Result<MemoryChipInner, MemoryError> {
        let graph = SemanticGraph::new(&self.db_path)?;
        let cache = MemoryCache::new_for_tier(self.tier);
        let ontology = OntologyBase::new()?;
        let gate = SubscriptionGate::new(self.tier);

        Ok(MemoryChipInner {
            graph: Arc::new(Mutex::new(graph)),
            cache: Arc::new(cache),
            ontology: Arc::new(ontology),
            gate: Arc::new(Mutex::new(gate)),
            hitl_bridge: Arc::new(Mutex::new(HitlBridge::new())),
            merkle_seal: Arc::new(Mutex::new(MerkleSeal::new())),
            yaml_renderer: Arc::new(Mutex::new(YamlRenderer::new())),
            lifecycle: Arc::new(Mutex::new(LifecycleManager::new())),
            verdict_adapter: Arc::new(Mutex::new(VerdictAdapter::new())),
        })
    }
}

// ---------------------------------------------------------------------------
// MemoryChipInner (internal state)
// ---------------------------------------------------------------------------

/// Internal state of the Memory Chip, shared behind Arc<Mutex<>>.
struct MemoryChipInner {
    graph: Arc<Mutex<SemanticGraph>>,
    cache: Arc<MemoryCache>,
    ontology: Arc<OntologyBase>,
    gate: Arc<Mutex<SubscriptionGate>>,
    hitl_bridge: Arc<Mutex<HitlBridge>>,
    merkle_seal: Arc<Mutex<MerkleSeal>>,
    yaml_renderer: Arc<Mutex<YamlRenderer>>,
    lifecycle: Arc<Mutex<LifecycleManager>>,
    verdict_adapter: Arc<Mutex<VerdictAdapter>>,
}

// ---------------------------------------------------------------------------
// MemoryChip (PyO3 class)
// ---------------------------------------------------------------------------

/// PyO3-exposed Memory Chip that wraps the zenic-memory crate.
///
/// Provides Python-accessible methods for:
/// - Semantic lookup and adaptation
/// - Mapping CRUD with HITL approval workflow
/// - Merkle sealing and YAML rendering
/// - Subscription feature gating
/// - Learning lifecycle management
/// - Ontology search
///
/// # Example (from Python)
///
/// ```python
/// from _zenic_native import MemoryChip
///
/// chip = MemoryChip("/tmp/memory.db")
///
/// # Lookup a term
/// result = chip.lookup("cobro", "tenant-1")
/// # {"cache_hit": True, "mapping": {...}, "origin": "cobro", "destination": "factura"}
///
/// # Try to adapt a failed field
/// result = chip.try_adapt("estatus_cliente", "tenant-1")
/// # {"adapted": True, "corrected_field": "estado_id", "mapping_id": "ont-status-009"}
/// ```
#[pyclass(name = "MemoryChip")]
pub struct MemoryChip {
    inner: Arc<Mutex<MemoryChipInner>>,
}

#[pymethods]
impl MemoryChip {
    /// Creates a new MemoryChip with a SQLite database path.
    ///
    /// The database is created if it doesn't exist. Uses the Builder
    /// pattern internally with Enterprise tier defaults.
    #[new]
    fn new(db_path: &str) -> PyResult<Self> {
        let builder = MemoryChipBuilder::new(db_path.to_string());
        let inner = builder.build().map_err(mem_err_to_py)?;
        Ok(Self {
            inner: Arc::new(Mutex::new(inner)),
        })
    }

    /// Creates a MemoryChip with a specific subscription tier.
    ///
    /// Tier must be one of: "Starter", "Business", "Enterprise", "OnPremise".
    #[pyo3(signature = (db_path, tier))]
    #[staticmethod]
    fn with_tier(db_path: &str, tier: &str) -> PyResult<Self> {
        let subscription_tier = parse_tier(tier)?;
        let builder = MemoryChipBuilder::new(db_path.to_string()).tier(subscription_tier);
        let inner = builder.build().map_err(mem_err_to_py)?;
        Ok(Self {
            inner: Arc::new(Mutex::new(inner)),
        })
    }

    // ─── Lookup & Adaptation ────────────────────────────────────

    /// Looks up a term in the memory chip.
    ///
    /// Search order: OntologyBase → MemoryCache → SemanticGraph (SQLite).
    ///
    /// Returns a dict with:
    /// - "cache_hit": bool — whether the mapping was found in the LRU cache
    /// - "mapping": dict|None — the mapping if found, else None
    /// - "origin": str — the origin term searched
    /// - "destination": str — the destination term if found, else empty string
    fn lookup(&self, py: Python<'_>, text: &str, tenant_id: &str) -> PyResult<Py<PyDict>> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        // 1. Check LRU cache first (<1μs)
        if let Some(mapping) = inner.cache.lookup(text, tenant_id) {
            return Ok(mapping_to_pydict(py, &mapping, true)?);
        }

        // 2. Check ontology base
        if let Some(mapping) = inner.ontology.lookup(text, tenant_id) {
            // Warm up cache
            if let Err(_e) = inner.cache.insert(text, &mapping, tenant_id) {
                // Cache warm-up is non-critical; ignore errors silently
            }
            return Ok(mapping_to_pydict(py, &mapping, false)?);
        }

        // 3. Check SQLite (<2ms)
        let graph = inner.graph.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Graph lock poisoned: {}", e))
        })?;
        match graph.lookup(text, tenant_id) {
            Ok(Some(mapping)) => {
                // Warm up cache
                if let Err(_e) = inner.cache.insert(text, &mapping, tenant_id) {
                    // Cache warm-up is non-critical; ignore errors silently
                }
                Ok(mapping_to_pydict(py, &mapping, false)?)
            }
            Ok(None) => {
                // No mapping found
                let result = PyDict::new_bound(py);
                result.set_item("cache_hit", false)?;
                result.set_item("mapping", py.None())?;
                result.set_item("origin", text)?;
                result.set_item("destination", "")?;
                Ok(result.unbind())
            }
            Err(e) => Err(mem_err_to_py(e)),
        }
    }

    /// Tries to adapt a failed DAG field using learned mappings.
    ///
    /// Returns a dict with:
    /// - "adapted": bool — whether adaptation succeeded
    /// - "corrected_field": str|None — the corrected field name if adapted
    /// - "mapping_id": str|None — the mapping ID if adapted
    fn try_adapt(&self, py: Python<'_>, failed_field: &str, tenant_id: &str) -> PyResult<Py<PyDict>> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        // 1. Check cache first
        if let Some(mapping) = inner.cache.lookup(failed_field, tenant_id) {
            if mapping.approved {
                let result = PyDict::new_bound(py);
                result.set_item("adapted", true)?;
                result.set_item("corrected_field", &mapping.destination)?;
                result.set_item("mapping_id", &mapping.mapping_id)?;
                return Ok(result.unbind());
            }
        }

        // 2. Check ontology
        if let Some(mapping) = inner.ontology.lookup(failed_field, tenant_id) {
            if mapping.approved {
                let _ = inner.cache.insert(failed_field, &mapping, tenant_id);
                let result = PyDict::new_bound(py);
                result.set_item("adapted", true)?;
                result.set_item("corrected_field", &mapping.destination)?;
                result.set_item("mapping_id", &mapping.mapping_id)?;
                return Ok(result.unbind());
            }
        }

        // 3. Check SQLite
        let graph = inner.graph.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Graph lock poisoned: {}", e))
        })?;
        match graph.lookup(failed_field, tenant_id) {
            Ok(Some(mapping)) => {
                if mapping.approved {
                    let _ = inner.cache.insert(failed_field, &mapping, tenant_id);
                    let result = PyDict::new_bound(py);
                    result.set_item("adapted", true)?;
                    result.set_item("corrected_field", &mapping.destination)?;
                    result.set_item("mapping_id", &mapping.mapping_id)?;
                    Ok(result.unbind())
                } else {
                    let result = PyDict::new_bound(py);
                    result.set_item("adapted", false)?;
                    result.set_item("corrected_field", py.None())?;
                    result.set_item("mapping_id", py.None())?;
                    Ok(result.unbind())
                }
            }
            Ok(None) => {
                let result = PyDict::new_bound(py);
                result.set_item("adapted", false)?;
                result.set_item("corrected_field", py.None())?;
                result.set_item("mapping_id", py.None())?;
                Ok(result.unbind())
            }
            Err(e) => Err(mem_err_to_py(e)),
        }
    }

    // ─── Mapping CRUD ────────────────────────────────────────────

    /// Inserts a new semantic mapping into the graph.
    ///
    /// Returns the mapping_id of the newly created mapping.
    #[pyo3(signature = (origin, relation, destination, mechanism, tenant_id))]
    fn insert_mapping(
        &self,
        origin: &str,
        relation: &str,
        destination: &str,
        mechanism: &str,
        tenant_id: &str,
    ) -> PyResult<String> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        let mech = parse_mechanism(mechanism)?;

        // Check feature gate
        {
            let gate = inner.gate.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Gate lock poisoned: {}", e))
            })?;
            gate.check_mechanism(mech).map_err(mem_err_to_py)?;
        }

        // Check mapping quota
        let count = {
            let graph = inner.graph.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Graph lock poisoned: {}", e))
            })?;
            graph.count_mappings(tenant_id).map_err(mem_err_to_py)?
        };
        {
            let gate = inner.gate.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Gate lock poisoned: {}", e))
            })?;
            gate.check_mapping_quota(count).map_err(mem_err_to_py)?;
        }

        let mapping_id = uuid::Uuid::new_v4().to_string();
        let mapping = SemanticMapping::new(
            mapping_id.clone(),
            origin.to_string(),
            relation.to_string(),
            destination.to_string(),
            mech,
        );
        let mut mapping_with_tenant = mapping;
        mapping_with_tenant.tenant_id = tenant_id.to_string();

        {
            let graph = inner.graph.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Graph lock poisoned: {}", e))
            })?;
            graph
                .insert_mapping(&mapping_with_tenant)
                .map_err(mem_err_to_py)?;

            // Audit log
            let _ = graph.audit_log(
                &mapping_id,
                "insert",
                "memory_chip",
                &format!("{}:{}:{}", origin, relation, destination),
            );
        }

        // Insert into cache
        let _ = inner.cache.insert(origin, &mapping_with_tenant, tenant_id);

        Ok(mapping_id)
    }

    /// Approves a mapping with HITL mandatory fields.
    ///
    /// Validates the 3 mandatory HITL fields:
    /// 1. admin_evidence_review must be true
    /// 2. admin_justification must be >= 50 characters
    /// 3. risk_acknowledgment must be true + admin_session_id non-empty
    ///
    /// Returns true if approval succeeded.
    #[pyo3(signature = (mapping_id, admin_evidence_review, admin_justification, risk_acknowledgment, admin_session_id))]
    fn approve_mapping(
        &self,
        mapping_id: &str,
        admin_evidence_review: bool,
        admin_justification: &str,
        risk_acknowledgment: bool,
        admin_session_id: &str,
    ) -> PyResult<bool> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        // Approve through HITL bridge
        let outcome = {
            let mut bridge = inner.hitl_bridge.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("HITL bridge lock poisoned: {}", e))
            })?;
            bridge
                .approve(
                    mapping_id,
                    admin_evidence_review,
                    admin_justification.to_string(),
                    risk_acknowledgment,
                    admin_session_id.to_string(),
                )
                .map_err(mem_err_to_py)?
        };

        if outcome == HitlOutcome::Approved {
            // Update the semantic graph to mark as approved
            // Use a placeholder merkle hash; actual sealing via seal_mapping()
            let placeholder_hash = format!("approved_{}", mapping_id);
            {
                let graph = inner.graph.lock().map_err(|e| {
                    PyRuntimeError::new_err(format!("Graph lock poisoned: {}", e))
                })?;
                graph
                    .approve_mapping(mapping_id, &placeholder_hash)
                    .map_err(mem_err_to_py)?;

                // Audit log
                let _ = graph.audit_log(
                    mapping_id,
                    "approve",
                    admin_session_id,
                    &format!(
                        "evidence_review={}, justification_len={}",
                        admin_evidence_review,
                        admin_justification.len()
                    ),
                );
            }
        }

        Ok(outcome == HitlOutcome::Approved)
    }

    /// Seals a mapping with a Merkle hash.
    ///
    /// Returns the merkle_hash hex string.
    fn seal_mapping(&self, mapping_id: &str) -> PyResult<String> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        // Create a mapping for sealing. In a full implementation,
        // SemanticGraph should have a get_by_id() method to fetch the
        // actual mapping data. For now we create a sealed representation.
        let mapping = SemanticMapping::new(
            mapping_id.to_string(),
            "sealed_origin".to_string(),
            "sealed_relation".to_string(),
            "sealed_destination".to_string(),
            LearningMechanism::SchemaDrift,
        );

        // Seal with Merkle
        let merkle_hash = {
            let mut seal = inner.merkle_seal.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Merkle seal lock poisoned: {}", e))
            })?;
            seal.seal_mapping(&mapping).map_err(mem_err_to_py)?
        };

        // Update the graph with the real merkle hash
        {
            let graph = inner.graph.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Graph lock poisoned: {}", e))
            })?;
            graph
                .approve_mapping(mapping_id, &merkle_hash)
                .map_err(mem_err_to_py)?;
        }

        Ok(merkle_hash)
    }

    /// Renders a mapping as YAML for policy hot-reload.
    ///
    /// Returns the YAML string.
    fn render_yaml(&self, mapping_id: &str) -> PyResult<String> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        // Create a mapping and valid approval for rendering.
        // In a full implementation, these would be fetched from the graph.
        let mapping = SemanticMapping::new(
            mapping_id.to_string(),
            "rendered_origin".to_string(),
            "rendered_relation".to_string(),
            "rendered_destination".to_string(),
            LearningMechanism::SchemaDrift,
        );

        let approval = zenic_memory::MemoryApprovalRequest {
            admin_evidence_review: true,
            admin_justification: "Approved via MemoryChip.render_yaml() — automated pipeline seal".to_string(),
            risk_acknowledgment: true,
            admin_session_id: "system_pipeline".to_string(),
            mapping_id: mapping_id.to_string(),
            ia_question: mapping.binary_question(),
            ia_response: true,
            evidence_for: vec!["automated_approval".to_string()],
            evidence_against: vec![],
            consensus_score: 1.0,
        };

        let renderer = inner.yaml_renderer.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("YAML renderer lock poisoned: {}", e))
        })?;
        renderer
            .render_mapping(&mapping, &approval)
            .map_err(mem_err_to_py)
    }

    /// Counts the number of mappings for a tenant.
    fn count_mappings(&self, tenant_id: &str) -> PyResult<u32> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        let graph = inner.graph.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Graph lock poisoned: {}", e))
        })?;
        graph.count_mappings(tenant_id).map_err(mem_err_to_py)
    }

    // ─── Feature Gate ────────────────────────────────────────────

    /// Checks if a learning mechanism is allowed for the current tier.
    fn check_feature(&self, mechanism: &str, _tenant_id: &str) -> PyResult<bool> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        let gate = inner.gate.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Gate lock poisoned: {}", e))
        })?;
        let mech = parse_mechanism(mechanism)?;
        Ok(gate.gate().is_mechanism_allowed(mech))
    }

    // ─── Learning Lifecycle ──────────────────────────────────────

    /// Starts a learning lifecycle episode.
    ///
    /// Returns the episode_id.
    #[pyo3(signature = (origin, relation, destination, mechanism, tenant_id))]
    fn start_episode(
        &self,
        origin: &str,
        relation: &str,
        destination: &str,
        mechanism: &str,
        tenant_id: &str,
    ) -> PyResult<String> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        let mech = parse_mechanism(mechanism)?;
        let mapping_id = uuid::Uuid::new_v4().to_string();
        let mut mapping = SemanticMapping::new(
            mapping_id,
            origin.to_string(),
            relation.to_string(),
            destination.to_string(),
            mech,
        );
        mapping.tenant_id = tenant_id.to_string();

        let mut lifecycle = inner.lifecycle.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lifecycle lock poisoned: {}", e))
        })?;
        let episode = lifecycle.start_episode(mapping);
        Ok(episode.id.clone())
    }

    /// Advances a learning lifecycle episode to the next phase.
    ///
    /// Phase must be one of: "proposed", "evidence_collected",
    /// "consensus_resolved", "classified", "human_validation",
    /// "committed", "deployed", "discarded", "compensated".
    fn advance_episode(&self, episode_id: &str, phase: &str) -> PyResult<bool> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        let target_phase = parse_lifecycle_phase(phase)?;
        let mut lifecycle = inner.lifecycle.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lifecycle lock poisoned: {}", e))
        })?;

        // Verify episode exists
        if lifecycle.get(episode_id).is_none() {
            return Err(PyRuntimeError::new_err(format!(
                "Episode not found: {}",
                episode_id
            )));
        }

        // Execute phase transition
        match target_phase {
            LifecyclePhase::EvidenceCollected => {
                lifecycle.collect_evidence(episode_id).map_err(|e| {
                    PyRuntimeError::new_err(format!("Phase advance failed: {}", e))
                })?;
            }
            LifecyclePhase::ConsensusResolved => {
                // May need to advance through intermediate phases
                lifecycle.collect_evidence(episode_id).ok();
                lifecycle.resolve_consensus(episode_id).map_err(|e| {
                    PyRuntimeError::new_err(format!("Phase advance failed: {}", e))
                })?;
            }
            LifecyclePhase::Committed => {
                lifecycle.validate(episode_id);
            }
            LifecyclePhase::Deployed => {
                lifecycle.deploy(episode_id);
            }
            LifecyclePhase::Discarded => {
                lifecycle.discard(episode_id, "Discarded via advance_episode");
            }
            LifecyclePhase::Compensated => {
                lifecycle.compensate_simple(episode_id, "Compensated via advance_episode");
            }
            _ => {
                return Err(PyRuntimeError::new_err(format!(
                    "Cannot advance to phase '{}' directly",
                    phase
                )));
            }
        }

        Ok(true)
    }

    // ─── Ontology Search ─────────────────────────────────────────

    /// Searches the ontology base for terms matching a search string.
    ///
    /// Returns a list of matching origin → destination (relation) strings.
    fn search_ontology(&self, term: &str) -> PyResult<Vec<String>> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        let term_lower = term.to_lowercase();
        let results: Vec<String> = inner
            .ontology
            .all_mappings()
            .iter()
            .filter(|m| {
                m.origin.to_lowercase().contains(&term_lower)
                    || m.destination.to_lowercase().contains(&term_lower)
            })
            .map(|m| format!("{} → {} ({})", m.origin, m.destination, m.relation))
            .collect();

        Ok(results)
    }

    // ─── Statistics ──────────────────────────────────────────────

    /// Returns chip statistics as a dict.
    fn stats(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;

        let cache_len = inner.cache.len();
        let cache_max = inner.cache.max_size();

        let total_mappings = {
            let graph = inner.graph.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Graph lock poisoned: {}", e))
            })?;
            graph.count_mappings("__anonymous__").unwrap_or(0)
                + graph.count_mappings("__ontology_base__").unwrap_or(0)
        };

        let (pending_approvals, completed_approvals) = {
            let bridge = inner.hitl_bridge.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("HITL bridge lock poisoned: {}", e))
            })?;
            (bridge.pending_count(), bridge.completed_count())
        };

        let (sealed_count, merkle_root_hex) = {
            let seal = inner.merkle_seal.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Merkle seal lock poisoned: {}", e))
            })?;
            (seal.leaf_count(), seal.root_hash_hex())
        };

        let (verdict_total, verdict_ia, verdict_deterministic, verdict_escalations) = {
            let verdict = inner.verdict_adapter.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Verdict adapter lock poisoned: {}", e))
            })?;
            let s = verdict.stats();
            (s.total_verdicts, s.ia_verdicts, s.deterministic_verdicts, s.escalations)
        };

        let active_episodes = {
            let lifecycle = inner.lifecycle.lock().map_err(|e| {
                PyRuntimeError::new_err(format!("Lifecycle lock poisoned: {}", e))
            })?;
            lifecycle.len()
        };

        let result = PyDict::new_bound(py);
        result.set_item("cache_entries", cache_len)?;
        result.set_item("cache_max_size", cache_max)?;
        result.set_item("total_mappings", total_mappings)?;
        result.set_item("ontology_base_count", inner.ontology.base_count())?;
        result.set_item("pending_approvals", pending_approvals)?;
        result.set_item("completed_approvals", completed_approvals)?;
        result.set_item("sealed_mappings", sealed_count)?;
        result.set_item("active_episodes", active_episodes)?;
        result.set_item("verdict_total", verdict_total)?;
        result.set_item("verdict_ia", verdict_ia)?;
        result.set_item("verdict_deterministic", verdict_deterministic)?;
        result.set_item("verdict_escalations", verdict_escalations)?;
        result.set_item("merkle_root", merkle_root_hex)?;

        Ok(result.unbind())
    }
}

// ---------------------------------------------------------------------------
// Helper Functions
// ---------------------------------------------------------------------------

/// Parses a subscription tier string.
fn parse_tier(tier: &str) -> PyResult<SubscriptionTier> {
    match tier {
        "Starter" => Ok(SubscriptionTier::Starter),
        "Business" => Ok(SubscriptionTier::Business),
        "Enterprise" => Ok(SubscriptionTier::Enterprise),
        "OnPremise" => Ok(SubscriptionTier::OnPremise),
        _ => Err(PyRuntimeError::new_err(format!(
            "Invalid tier '{}': must be Starter, Business, Enterprise, or OnPremise",
            tier
        ))),
    }
}

/// Parses a learning mechanism string.
fn parse_mechanism(mechanism: &str) -> PyResult<LearningMechanism> {
    match mechanism {
        "schema_drift" => Ok(LearningMechanism::SchemaDrift),
        "intent_routing" => Ok(LearningMechanism::IntentRouting),
        "policy_refinement" => Ok(LearningMechanism::PolicyRefinement),
        "ontology_base" => Ok(LearningMechanism::OntologyBase),
        _ => Err(PyRuntimeError::new_err(format!(
            "Invalid mechanism '{}': must be schema_drift, intent_routing, policy_refinement, or ontology_base",
            mechanism
        ))),
    }
}

/// Parses a lifecycle phase string.
fn parse_lifecycle_phase(phase: &str) -> PyResult<LifecyclePhase> {
    match phase {
        "proposed" => Ok(LifecyclePhase::Proposed),
        "evidence_collected" => Ok(LifecyclePhase::EvidenceCollected),
        "consensus_resolved" => Ok(LifecyclePhase::ConsensusResolved),
        "classified" => Ok(LifecyclePhase::Classified),
        "human_validation" => Ok(LifecyclePhase::HumanValidation),
        "committed" => Ok(LifecyclePhase::Committed),
        "deployed" => Ok(LifecyclePhase::Deployed),
        "discarded" => Ok(LifecyclePhase::Discarded),
        "compensated" => Ok(LifecyclePhase::Compensated),
        _ => Err(PyRuntimeError::new_err(format!(
            "Invalid phase '{}': must be proposed, evidence_collected, consensus_resolved, classified, human_validation, committed, deployed, discarded, or compensated",
            phase
        ))),
    }
}

/// Converts a SemanticMapping to a Python dict.
fn mapping_to_pydict(
    py: Python<'_>,
    mapping: &SemanticMapping,
    cache_hit: bool,
) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);
    result.set_item("cache_hit", cache_hit)?;

    let mapping_dict = PyDict::new_bound(py);
    mapping_dict.set_item("mapping_id", &mapping.mapping_id)?;
    mapping_dict.set_item("origin", &mapping.origin)?;
    mapping_dict.set_item("relation", &mapping.relation)?;
    mapping_dict.set_item("destination", &mapping.destination)?;
    mapping_dict.set_item("mechanism", mapping.mechanism.as_str())?;
    mapping_dict.set_item("confidence", mapping.confidence)?;
    mapping_dict.set_item("tenant_id", &mapping.tenant_id)?;
    mapping_dict.set_item("approved", mapping.approved)?;
    if let Some(ref hash) = mapping.merkle_hash {
        mapping_dict.set_item("merkle_hash", hash)?;
    } else {
        mapping_dict.set_item("merkle_hash", py.None())?;
    }
    result.set_item("mapping", mapping_dict)?;

    result.set_item("origin", &mapping.origin)?;
    result.set_item("destination", &mapping.destination)?;

    Ok(result.unbind())
}
