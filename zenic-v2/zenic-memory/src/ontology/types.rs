//! Shared Ontology Layer: OntologyBase type and implementation.

use std::collections::HashMap;
use std::sync::RwLock;

use crate::errors::MemoryError;
use crate::types::SemanticMapping;

// ---------------------------------------------------------------------------
// OntologyBase
// ---------------------------------------------------------------------------

/// Shared Ontology Base — universal mappings available to all tenants.
///
/// Loaded from embedded data at startup. Tenants can opt-in to override
/// specific base mappings with their own custom definitions.
///
/// # Thread Safety
///
/// Uses `RwLock` for the tenant overrides map, allowing concurrent reads
/// of base mappings and safe mutation of tenant-specific overrides.
pub struct OntologyBase {
    /// Base mappings available to all tenants.
    pub(super) mappings: Vec<SemanticMapping>,
    /// Per-tenant overrides. Key is `tenant_id`, value is a list of
    /// mappings that take priority over the base mappings.
    pub(super) tenant_overrides: RwLock<HashMap<String, Vec<SemanticMapping>>>,
}

impl OntologyBase {
    /// Creates a new ontology base with built-in mappings.
    ///
    /// In a production system, this would load from an embedded YAML file
    /// (`base-es.yaml`). For now, it uses the hardcoded built-in mappings.
    pub fn new() -> Result<Self, MemoryError> {
        let mappings = Self::load_builtin();
        Ok(Self {
            mappings,
            tenant_overrides: RwLock::new(HashMap::new()),
        })
    }

    /// Looks up a term in the ontology with tenant override priority.
    ///
    /// Lookup order:
    /// 1. Tenant overrides (if any match the origin term).
    /// 2. Base mappings.
    ///
    /// Returns the first match found, or `None` if the term is not in
    /// the ontology.
    pub fn lookup(&self, term: &str, tenant_id: &str) -> Option<SemanticMapping> {
        // 1. Check tenant overrides first.
        if let Ok(overrides) = self.tenant_overrides.read() {
            if let Some(tenant_mappings) = overrides.get(tenant_id) {
                if let Some(mapping) = tenant_mappings.iter().find(|m| m.origin == term) {
                    return Some(mapping.clone());
                }
            }
        }

        // 2. Fall back to base mappings.
        self.mappings
            .iter()
            .find(|m| m.origin == term)
            .cloned()
    }

    /// Adds a tenant-specific override for a base mapping.
    ///
    /// Tenant overrides take priority over base mappings during lookup.
    /// This allows tenants to customize the ontology without affecting
    /// other tenants.
    pub fn add_tenant_override(
        &self,
        tenant_id: &str,
        mapping: SemanticMapping,
    ) -> Result<(), MemoryError> {
        let mut overrides = self.tenant_overrides.write().map_err(|e| {
            MemoryError::Internal(format!("tenant_overrides write lock poisoned: {}", e))
        })?;

        overrides
            .entry(tenant_id.to_string())
            .or_insert_with(Vec::new)
            .push(mapping);

        Ok(())
    }

    /// Returns a reference to all base mappings.
    pub fn all_mappings(&self) -> &[SemanticMapping] {
        &self.mappings
    }

    /// Returns the number of base mappings.
    pub fn base_count(&self) -> usize {
        self.mappings.len()
    }

    /// Returns the number of tenant overrides for a specific tenant.
    pub fn override_count(&self, tenant_id: &str) -> usize {
        self.tenant_overrides
            .read()
            .map(|o| o.get(tenant_id).map_or(0, |v| v.len()))
            .unwrap_or(0)
    }
}

impl Default for OntologyBase {
    fn default() -> Self {
        Self::new().expect("OntologyBase::new should never fail with built-in mappings")
    }
}
