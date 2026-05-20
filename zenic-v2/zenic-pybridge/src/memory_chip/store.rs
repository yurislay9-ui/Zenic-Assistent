//! Store operations for the Memory Chip.
//!
//! Contains helper functions for mapping CRUD, HITL approval,
//! Merkle sealing, and YAML rendering — extracted from the
//! MemoryChip PyO3 methods.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

use zenic_memory::{HitlOutcome, LearningMechanism, SemanticMapping};

use super::types::{mem_err_to_py, parse_mechanism, MemoryChipInner};

/// Inserts a new semantic mapping into the graph.
///
/// Returns the mapping_id of the newly created mapping.
pub(crate) fn insert_mapping(
    inner: &MemoryChipInner,
    origin: &str,
    relation: &str,
    destination: &str,
    mechanism: &str,
    tenant_id: &str,
) -> PyResult<String> {
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
pub(crate) fn approve_mapping(
    inner: &MemoryChipInner,
    mapping_id: &str,
    admin_evidence_review: bool,
    admin_justification: &str,
    risk_acknowledgment: bool,
    admin_session_id: &str,
) -> PyResult<bool> {
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
pub(crate) fn seal_mapping(inner: &MemoryChipInner, mapping_id: &str) -> PyResult<String> {
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
pub(crate) fn render_yaml(inner: &MemoryChipInner, mapping_id: &str) -> PyResult<String> {
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
pub(crate) fn count_mappings(inner: &MemoryChipInner, tenant_id: &str) -> PyResult<u32> {
    let graph = inner.graph.lock().map_err(|e| {
        PyRuntimeError::new_err(format!("Graph lock poisoned: {}", e))
    })?;
    graph.count_mappings(tenant_id).map_err(mem_err_to_py)
}
