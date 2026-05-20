//! Shared types, builders, parsers, and helpers for the memory_chip module.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::sync::{Arc, Mutex};

use zenic_memory::{
    HitlOutcome, LearningMechanism, LifecyclePhase, MemoryCache, MemoryError, OntologyBase,
    SemanticGraph, SemanticMapping, SubscriptionGate, SubscriptionTier, HitlBridge, MerkleSeal,
    YamlRenderer, LifecycleManager, VerdictAdapter,
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
pub(crate) fn mem_err_to_py(e: MemoryError) -> PyErr {
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
pub(crate) struct MemoryChipInner {
    pub graph: Arc<Mutex<SemanticGraph>>,
    pub cache: Arc<MemoryCache>,
    pub ontology: Arc<OntologyBase>,
    pub gate: Arc<Mutex<SubscriptionGate>>,
    pub hitl_bridge: Arc<Mutex<HitlBridge>>,
    pub merkle_seal: Arc<Mutex<MerkleSeal>>,
    pub yaml_renderer: Arc<Mutex<YamlRenderer>>,
    pub lifecycle: Arc<Mutex<LifecycleManager>>,
    pub verdict_adapter: Arc<Mutex<VerdictAdapter>>,
}

// ---------------------------------------------------------------------------
// Helper Functions
// ---------------------------------------------------------------------------

/// Parses a subscription tier string.
pub(crate) fn parse_tier(tier: &str) -> PyResult<SubscriptionTier> {
    match tier {
        "Starter" => Ok(SubscriptionTier::Starter),
        "Business" => Ok(SubscriptionTier::Business),
        "Enterprise" => Ok(SubscriptionTier::Enterprise),
        "OnPremiseEnterprise" | "OnPremise" => Ok(SubscriptionTier::OnPremiseEnterprise),
        _ => Err(PyRuntimeError::new_err(format!(
            "Invalid tier '{}': must be Starter, Business, Enterprise, or OnPremiseEnterprise",
            tier
        ))),
    }
}

/// Parses a learning mechanism string.
pub(crate) fn parse_mechanism(mechanism: &str) -> PyResult<LearningMechanism> {
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
pub(crate) fn parse_lifecycle_phase(phase: &str) -> PyResult<LifecyclePhase> {
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
pub(crate) fn mapping_to_pydict(
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
