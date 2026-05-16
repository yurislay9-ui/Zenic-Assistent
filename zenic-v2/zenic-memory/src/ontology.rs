//! Shared Ontology Layer.
//!
//! Loads base mappings from embedded data and provides opt-in per-tenant
//! access. The ontology serves as the universal foundation of semantic
//! knowledge that all tenants can reference.
//!
//! ## Architecture
//!
//! ```text
//! ┌─────────────────────────────────────────────┐
//! │               OntologyBase                  │
//! │  ┌───────────────────────────────────────┐  │
//! │  │  Base Mappings (~50 Spanish terms)    │  │
//! │  │  tenant_id = "__ontology_base__"      │  │
//! │  │  confidence = 80, approved = true     │  │
//! │  └───────────────────────────────────────┘  │
//! │  ┌───────────────────────────────────────┐  │
//! │  │  Tenant Overrides (opt-in)            │  │
//! │  │  tenant_id = "<specific_tenant>"      │  │
//! │  │  Takes priority over base mappings    │  │
//! │  └───────────────────────────────────────┘  │
//! └─────────────────────────────────────────────┘
//! ```
//!
//! ## Lookup Priority
//!
//! When looking up a term, tenant overrides take priority over base
//! mappings. This allows tenants to customize the ontology without
//! affecting other tenants.

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
    mappings: Vec<SemanticMapping>,
    /// Per-tenant overrides. Key is `tenant_id`, value is a list of
    /// mappings that take priority over the base mappings.
    tenant_overrides: RwLock<HashMap<String, Vec<SemanticMapping>>>,
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

    /// Returns the built-in Spanish business term mappings.
    ///
    /// These ~50 mappings cover financial terms, status/state terms,
    /// action terms, business terms, and urgency/priority terms in
    /// Latin American Spanish business contexts.
    pub fn load_builtin() -> Vec<SemanticMapping> {
        vec![
            // =================================================================
            // Financial Terms (10)
            // =================================================================
            SemanticMapping::ontology_base(
                "ont-fin-001".to_string(),
                "cobro".to_string(),
                "synonym_of".to_string(),
                "factura".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-fin-002".to_string(),
                "pago".to_string(),
                "synonym_of".to_string(),
                "transacción".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-fin-003".to_string(),
                "cuenta".to_string(),
                "synonym_of".to_string(),
                "perfil_cliente".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-fin-004".to_string(),
                "saldo".to_string(),
                "synonym_of".to_string(),
                "balance".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-fin-005".to_string(),
                "factura".to_string(),
                "broader_than".to_string(),
                "documento_tributario".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-fin-006".to_string(),
                "abono".to_string(),
                "synonym_of".to_string(),
                "deposito".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-fin-007".to_string(),
                "cargo".to_string(),
                "synonym_of".to_string(),
                "debito".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-fin-008".to_string(),
                "beneficio".to_string(),
                "synonym_of".to_string(),
                "ganancia".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-fin-009".to_string(),
                "perdida".to_string(),
                "synonym_of".to_string(),
                "deficit".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-fin-010".to_string(),
                "factura".to_string(),
                "synonym_of".to_string(),
                "recibo".to_string(),
            ),

            // =================================================================
            // Status/State Terms (10)
            // =================================================================
            SemanticMapping::ontology_base(
                "ont-status-001".to_string(),
                "estatus".to_string(),
                "synonym_of".to_string(),
                "estado".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-status-002".to_string(),
                "activo".to_string(),
                "synonym_of".to_string(),
                "vigente".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-status-003".to_string(),
                "inactivo".to_string(),
                "synonym_of".to_string(),
                "suspendido".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-status-004".to_string(),
                "cancelado".to_string(),
                "synonym_of".to_string(),
                "anulado".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-status-005".to_string(),
                "pendiente".to_string(),
                "synonym_of".to_string(),
                "en_espera".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-status-006".to_string(),
                "aprobado".to_string(),
                "synonym_of".to_string(),
                "autorizado".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-status-007".to_string(),
                "rechazado".to_string(),
                "synonym_of".to_string(),
                "denegado".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-status-008".to_string(),
                "cerrado".to_string(),
                "synonym_of".to_string(),
                "finalizado".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-status-009".to_string(),
                "estatus_cliente".to_string(),
                "maps_to".to_string(),
                "estado_id".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-status-010".to_string(),
                "estatus_pedido".to_string(),
                "maps_to".to_string(),
                "pedido_estado".to_string(),
            ),

            // =================================================================
            // Action Terms (10)
            // =================================================================
            SemanticMapping::ontology_base(
                "ont-act-001".to_string(),
                "tumba".to_string(),
                "action_for".to_string(),
                "cancelar".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-act-002".to_string(),
                "baja".to_string(),
                "action_for".to_string(),
                "desactivar".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-act-003".to_string(),
                "alta".to_string(),
                "action_for".to_string(),
                "activar".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-act-004".to_string(),
                "borra".to_string(),
                "action_for".to_string(),
                "eliminar".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-act-005".to_string(),
                "quita".to_string(),
                "action_for".to_string(),
                "remover".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-act-006".to_string(),
                "pon".to_string(),
                "action_for".to_string(),
                "agregar".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-act-007".to_string(),
                "cambia".to_string(),
                "action_for".to_string(),
                "modificar".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-act-008".to_string(),
                "arregla".to_string(),
                "action_for".to_string(),
                "reparar".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-act-009".to_string(),
                "revisa".to_string(),
                "action_for".to_string(),
                "verificar".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-act-010".to_string(),
                "manda".to_string(),
                "action_for".to_string(),
                "enviar".to_string(),
            ),

            // =================================================================
            // Business Terms (10)
            // =================================================================
            SemanticMapping::ontology_base(
                "ont-biz-001".to_string(),
                "cliente".to_string(),
                "synonym_of".to_string(),
                "comprador".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-biz-002".to_string(),
                "proveedor".to_string(),
                "synonym_of".to_string(),
                "vendedor".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-biz-003".to_string(),
                "empleado".to_string(),
                "synonym_of".to_string(),
                "trabajador".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-biz-004".to_string(),
                "producto".to_string(),
                "synonym_of".to_string(),
                "articulo".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-biz-005".to_string(),
                "servicio".to_string(),
                "broader_than".to_string(),
                "oferta".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-biz-006".to_string(),
                "inventario".to_string(),
                "synonym_of".to_string(),
                "stock".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-biz-007".to_string(),
                "pedido".to_string(),
                "synonym_of".to_string(),
                "orden".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-biz-008".to_string(),
                "entrega".to_string(),
                "synonym_of".to_string(),
                "despacho".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-biz-009".to_string(),
                "descuento".to_string(),
                "synonym_of".to_string(),
                "rebaja".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-biz-010".to_string(),
                "impuesto".to_string(),
                "synonym_of".to_string(),
                "tributo".to_string(),
            ),

            // =================================================================
            // Urgency/Priority Terms (10)
            // =================================================================
            SemanticMapping::ontology_base(
                "ont-pri-001".to_string(),
                "urgente".to_string(),
                "priority_level".to_string(),
                "critico".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-pri-002".to_string(),
                "importante".to_string(),
                "priority_level".to_string(),
                "alto".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-pri-003".to_string(),
                "rapido".to_string(),
                "priority_level".to_string(),
                "alto".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-pri-004".to_string(),
                "inmediato".to_string(),
                "priority_level".to_string(),
                "critico".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-pri-005".to_string(),
                "reparacion_urgente".to_string(),
                "maps_to".to_string(),
                "gasto_critico".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-pri-006".to_string(),
                "averia".to_string(),
                "synonym_of".to_string(),
                "falla".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-pri-007".to_string(),
                "emergencia".to_string(),
                "priority_level".to_string(),
                "critico".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-pri-008".to_string(),
                "normal".to_string(),
                "priority_level".to_string(),
                "medio".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-pri-009".to_string(),
                "baja_prioridad".to_string(),
                "priority_level".to_string(),
                "bajo".to_string(),
            ),
            SemanticMapping::ontology_base(
                "ont-pri-010".to_string(),
                "pronto".to_string(),
                "priority_level".to_string(),
                "alto".to_string(),
            ),
        ]
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

// ---------------------------------------------------------------------------
// Default
// ---------------------------------------------------------------------------

impl Default for OntologyBase {
    fn default() -> Self {
        Self::new().expect("OntologyBase::new should never fail with built-in mappings")
    }
}
