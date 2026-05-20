//! Retrieval operations for the Memory Chip.
//!
//! Contains helper functions for lookup, adaptation, search, stats,
//! and feature gating — extracted from the MemoryChip PyO3 methods.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::types::{mapping_to_pydict, mem_err_to_py, parse_mechanism, MemoryChipInner};

/// Looks up a term in the memory chip.
///
/// Search order: OntologyBase → MemoryCache → SemanticGraph (SQLite).
///
/// Returns a dict with:
/// - "cache_hit": bool — whether the mapping was found in the LRU cache
/// - "mapping": dict|None — the mapping if found, else None
/// - "origin": str — the origin term searched
/// - "destination": str — the destination term if found, else empty string
pub(crate) fn lookup(
    inner: &MemoryChipInner,
    py: Python<'_>,
    text: &str,
    tenant_id: &str,
) -> PyResult<Py<PyDict>> {
    // 1. Check LRU cache first (<1μs)
    if let Some(mapping) = inner.cache.lookup(text, tenant_id) {
        return mapping_to_pydict(py, &mapping, true);
    }

    // 2. Check ontology base
    if let Some(mapping) = inner.ontology.lookup(text, tenant_id) {
        // Warm up cache
        if let Err(_e) = inner.cache.insert(text, &mapping, tenant_id) {
            // Cache warm-up is non-critical; ignore errors silently
        }
        return mapping_to_pydict(py, &mapping, false);
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
            mapping_to_pydict(py, &mapping, false)
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
pub(crate) fn try_adapt(
    inner: &MemoryChipInner,
    py: Python<'_>,
    failed_field: &str,
    tenant_id: &str,
) -> PyResult<Py<PyDict>> {
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

/// Searches the ontology base for terms matching a search string.
///
/// Returns a list of matching origin → destination (relation) strings.
pub(crate) fn search_ontology(inner: &MemoryChipInner, term: &str) -> PyResult<Vec<String>> {
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

/// Checks if a learning mechanism is allowed for the current tier.
pub(crate) fn check_feature(inner: &MemoryChipInner, mechanism: &str) -> PyResult<bool> {
    let gate = inner.gate.lock().map_err(|e| {
        PyRuntimeError::new_err(format!("Gate lock poisoned: {}", e))
    })?;
    let mech = parse_mechanism(mechanism)?;
    Ok(gate.gate().is_mechanism_allowed(mech))
}

/// Returns chip statistics as a dict.
pub(crate) fn stats(inner: &MemoryChipInner, py: Python<'_>) -> PyResult<Py<PyDict>> {
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
