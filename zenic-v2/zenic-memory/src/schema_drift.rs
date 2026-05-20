//! Schema Drift Detection — Mechanism 1 [T1-4, T1-7]
//!
//! Detects when database schema field names diverge from what the DAG expects.
//! Example: "estatus_cliente" → "estado_id"
//!
//! Schema Drift is the most common learning mechanism. It fires when:
//! - A node fails because a field name doesn't match the DB schema
//! - The user uses a synonym that the system doesn't recognize
//! - A DB migration renamed a column
//!
//! Resolution: The Chip proposes a mapping (hypothesis), the IA classifies
//! YES/NO, and a human validates. Next time, resolved in Layer 1 <5ms.

use crate::errors::MemoryError;
use crate::graph::SemanticGraph;
use crate::hypothesis::HypothesisManager;
use crate::ontology::OntologyBase;
use crate::types::{Hypothesis, LearningMechanism, SemanticMapping};

// ---------------------------------------------------------------------------
// DriftEvent
// ---------------------------------------------------------------------------

/// A detected schema drift event.
#[derive(Debug, Clone)]
pub struct DriftEvent {
    /// The field name that caused the drift.
    pub field: String,
    /// The expected field name in the schema.
    pub expected: String,
    /// Description of the drift.
    pub description: String,
    /// Severity: 1 = cosmetic, 5 = blocking execution.
    pub severity: u8,
    /// The tenant where this drift was detected.
    pub tenant_id: String,
}

// ---------------------------------------------------------------------------
// SchemaDriftDetector
// ---------------------------------------------------------------------------

/// Schema Drift Detector — Mechanism 1 of the Chip de Memoria Adaptativa.
///
/// Monitors for structural schema changes and generates hypotheses
/// when a field name doesn't match what the DAG expects.
pub struct SchemaDriftDetector {
    /// Known field names in the expected schema.
    known_fields: Vec<String>,
    /// Accumulated drift events.
    events: Vec<DriftEvent>,
    /// Reference to the hypothesis manager.
    hypothesis_mgr: Option<HypothesisManager>,
}

impl SchemaDriftDetector {
    /// Creates a new drift detector with the given known field names.
    pub fn new(known_fields: Vec<String>) -> Self {
        Self {
            known_fields,
            events: Vec::new(),
            hypothesis_mgr: None,
        }
    }

    /// Creates a drift detector with common business fields.
    pub fn with_default_fields() -> Self {
        Self::new(vec![
            "estado_id".to_string(),
            "factura".to_string(),
            "cliente_id".to_string(),
            "pedido_estado".to_string(),
            "monto_total".to_string(),
            "fecha_creacion".to_string(),
            "metodo_pago".to_string(),
            "direccion_envio".to_string(),
            "telefono_contacto".to_string(),
            "correo_electronico".to_string(),
        ])
    }

    /// Sets the hypothesis manager reference.
    pub fn set_hypothesis_manager(&mut self, mgr: HypothesisManager) {
        self.hypothesis_mgr = Some(mgr);
    }

    /// Detects schema drift by checking if a field name exists in the known schema.
    ///
    /// If the field is unknown, it generates a drift event and potentially
    /// a hypothesis if the ontology has a candidate mapping.
    pub fn detect_drift(
        &mut self,
        field: &str,
        tenant_id: &str,
        ontology: &OntologyBase,
    ) -> Option<DriftEvent> {
        // Skip if the field is already known
        if self.known_fields.iter().any(|f| f.eq_ignore_ascii_case(field)) {
            return None;
        }

        // Check if the ontology has a mapping for this field
        if let Some(mapping) = ontology.lookup(field, tenant_id) {
            let event = DriftEvent {
                field: field.to_string(),
                expected: mapping.destination.clone(),
                description: format!(
                    "Field '{}' maps to '{}' (confidence: {}%)",
                    field, mapping.destination, mapping.confidence
                ),
                severity: if mapping.approved { 1 } else { 3 },
                tenant_id: tenant_id.to_string(),
            };
            self.events.push(event.clone());
            Some(event)
        } else {
            // No mapping found — high severity drift
            let event = DriftEvent {
                field: field.to_string(),
                expected: String::new(),
                description: format!(
                    "Unknown field '{}' — no mapping found in ontology or memory",
                    field
                ),
                severity: 5,
                tenant_id: tenant_id.to_string(),
            };
            self.events.push(event.clone());
            Some(event)
        }
    }

    /// Generates a Schema Drift hypothesis from a drift event.
    ///
    /// This is called when the deterministic layer detects friction
    /// but the ontology doesn't have a pre-approved mapping.
    pub fn generate_hypothesis(
        &mut self,
        field: &str,
        suggested_destination: &str,
        context: &str,
    ) -> Result<Hypothesis, MemoryError> {
        if let Some(ref mut mgr) = self.hypothesis_mgr {
            mgr.generate_schema_drift(field, suggested_destination, context)?;
            Ok(mgr.pending().last().unwrap().clone())
        } else {
            // No hypothesis manager — create inline
            Ok(Hypothesis::new(
                field,
                "maps_to",
                suggested_destination,
                LearningMechanism::SchemaDrift,
                context,
                0.5,
            ))
        }
    }

    /// Attempts to reconcile a drift event by looking up existing mappings.
    pub fn try_reconcile(
        &self,
        event: &DriftEvent,
        graph: &SemanticGraph,
        tenant_id: &str,
    ) -> Result<Option<SemanticMapping>, MemoryError> {
        // Look up the field in the semantic graph
        match graph.lookup(&event.field, tenant_id) {
            Ok(Some(mapping)) if mapping.approved => Ok(Some(mapping)),
            Ok(Some(_)) => Ok(None), // Mapping exists but not approved
            Ok(None) => Ok(None),     // No mapping found
            Err(e) => Err(e),
        }
    }

    /// Returns all recorded drift events.
    pub fn events(&self) -> &[DriftEvent] {
        &self.events
    }

    /// Returns drift events filtered by severity.
    pub fn events_by_severity(&self, min_severity: u8) -> Vec<&DriftEvent> {
        self.events.iter().filter(|e| e.severity >= min_severity).collect()
    }

    /// Clears all drift events.
    pub fn clear_events(&mut self) {
        self.events.clear();
    }

    /// Adds a known field to the schema.
    pub fn add_known_field(&mut self, field: String) {
        if !self.known_fields.iter().any(|f| f.eq_ignore_ascii_case(&field)) {
            self.known_fields.push(field);
        }
    }

    /// Returns the known fields.
    pub fn known_fields(&self) -> &[String] {
        &self.known_fields
    }
}
