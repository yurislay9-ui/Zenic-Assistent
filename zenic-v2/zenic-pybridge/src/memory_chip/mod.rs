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

pub mod lifecycle;
pub mod retrieval;
pub mod store;
pub mod types;

pub use types::theorem_cache_deserialize;
pub use types::theorem_cache_serialize;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use std::sync::{Arc, Mutex};

use types::{mem_err_to_py, parse_tier, MemoryChipBuilder, MemoryChipInner};

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
    /// Tier must be one of: "Starter", "Business", "Enterprise", "OnPremiseEnterprise".
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
    fn lookup(&self, py: Python<'_>, text: &str, tenant_id: &str) -> PyResult<Py<PyDict>> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        retrieval::lookup(&inner, py, text, tenant_id)
    }

    /// Tries to adapt a failed DAG field using learned mappings.
    fn try_adapt(&self, py: Python<'_>, failed_field: &str, tenant_id: &str) -> PyResult<Py<PyDict>> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        retrieval::try_adapt(&inner, py, failed_field, tenant_id)
    }

    // ─── Mapping CRUD ────────────────────────────────────────────

    /// Inserts a new semantic mapping into the graph.
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
        store::insert_mapping(&inner, origin, relation, destination, mechanism, tenant_id)
    }

    /// Approves a mapping with HITL mandatory fields.
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
        store::approve_mapping(
            &inner,
            mapping_id,
            admin_evidence_review,
            admin_justification,
            risk_acknowledgment,
            admin_session_id,
        )
    }

    /// Seals a mapping with a Merkle hash.
    fn seal_mapping(&self, mapping_id: &str) -> PyResult<String> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        store::seal_mapping(&inner, mapping_id)
    }

    /// Renders a mapping as YAML for policy hot-reload.
    fn render_yaml(&self, mapping_id: &str) -> PyResult<String> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        store::render_yaml(&inner, mapping_id)
    }

    /// Counts the number of mappings for a tenant.
    fn count_mappings(&self, tenant_id: &str) -> PyResult<u32> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        store::count_mappings(&inner, tenant_id)
    }

    // ─── Feature Gate ────────────────────────────────────────────

    /// Checks if a learning mechanism is allowed for the current tier.
    fn check_feature(&self, mechanism: &str, _tenant_id: &str) -> PyResult<bool> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        retrieval::check_feature(&inner, mechanism)
    }

    // ─── Learning Lifecycle ──────────────────────────────────────

    /// Starts a learning lifecycle episode.
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
        lifecycle::start_episode(&inner, origin, relation, destination, mechanism, tenant_id)
    }

    /// Advances a learning lifecycle episode to the next phase.
    fn advance_episode(&self, episode_id: &str, phase: &str) -> PyResult<bool> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        lifecycle::advance_episode(&inner, episode_id, phase)
    }

    // ─── Ontology Search ─────────────────────────────────────────

    /// Searches the ontology base for terms matching a search string.
    fn search_ontology(&self, term: &str) -> PyResult<Vec<String>> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        retrieval::search_ontology(&inner, term)
    }

    // ─── Statistics ──────────────────────────────────────────────

    /// Returns chip statistics as a dict.
    fn stats(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let inner = self.inner.lock().map_err(|e| {
            PyRuntimeError::new_err(format!("Lock poisoned: {}", e))
        })?;
        retrieval::stats(&inner, py)
    }
}
