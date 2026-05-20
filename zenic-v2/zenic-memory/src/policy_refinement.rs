//! Policy Refinement — Mechanism 3 [T1-6, T1-9]
//!
//! Classifies gray-area security/business policy terms into canonical categories.
//! Example: "reparación urgente" → "gasto_crítico"
//!
//! When the Policy Engine encounters a term that doesn't fit neatly into
//! existing categories, the PolicyRefinementEngine proposes a classification
//! hypothesis. The IA classifies YES/NO, and a human validates.
//!
//! After approval, the YAML policy is hot-reloaded into zenic-policy.

use crate::errors::MemoryError;
use crate::graph::SemanticGraph;
use crate::hypothesis::HypothesisManager;
use crate::ontology::OntologyBase;
use crate::types::{Hypothesis, LearningMechanism};

// ---------------------------------------------------------------------------
// PolicyCategory
// ---------------------------------------------------------------------------

/// Canonical policy categories for classification.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PolicyCategory {
    /// Critical expense requiring immediate approval.
    GastoCritico,
    /// Normal operational expense.
    GastoOperativo,
    /// Security-sensitive operation.
    OperacionSegura,
    /// Potentially dangerous operation.
    OperacionRiesgosa,
    /// Standard business action.
    AccionNormal,
    /// Action requiring managerial approval.
    AccionGerencial,
    /// Unknown / unclassified.
    Unclassified,
}

impl PolicyCategory {
    /// Returns the canonical string key for this category.
    pub fn as_key(&self) -> &'static str {
        match self {
            Self::GastoCritico => "gasto_critico",
            Self::GastoOperativo => "gasto_operativo",
            Self::OperacionSegura => "operacion_segura",
            Self::OperacionRiesgosa => "operacion_riesgosa",
            Self::AccionNormal => "accion_normal",
            Self::AccionGerencial => "accion_gerencial",
            Self::Unclassified => "unclassified",
        }
    }

    /// Returns all defined categories.
    pub fn all() -> &'static [PolicyCategory] {
        &[
            Self::GastoCritico,
            Self::GastoOperativo,
            Self::OperacionSegura,
            Self::OperacionRiesgosa,
            Self::AccionNormal,
            Self::AccionGerencial,
        ]
    }

    /// Parses a category from a string key.
    pub fn from_key(s: &str) -> Self {
        match s {
            "gasto_critico" => Self::GastoCritico,
            "gasto_operativo" => Self::GastoOperativo,
            "operacion_segura" => Self::OperacionSegura,
            "operacion_riesgosa" => Self::OperacionRiesgosa,
            "accion_normal" => Self::AccionNormal,
            "accion_gerencial" => Self::AccionGerencial,
            _ => Self::Unclassified,
        }
    }

    /// Returns the risk level of this category (1-5).
    pub fn risk_level(&self) -> u8 {
        match self {
            Self::GastoCritico => 5,
            Self::OperacionRiesgosa => 4,
            Self::AccionGerencial => 3,
            Self::GastoOperativo => 2,
            Self::OperacionSegura | Self::AccionNormal => 1,
            Self::Unclassified => 3, // Default to medium risk
        }
    }
}

impl std::fmt::Display for PolicyCategory {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_key())
    }
}

// ---------------------------------------------------------------------------
// RefinementResult
// ---------------------------------------------------------------------------

/// Result of a policy refinement lookup.
#[derive(Debug, Clone)]
pub struct RefinementResult {
    /// The original term.
    pub original_term: String,
    /// The classified category.
    pub category: PolicyCategory,
    /// The relation that connected them.
    pub relation: String,
    /// Confidence of the classification (0.0–1.0).
    pub confidence: f64,
    /// Source of the classification.
    pub source: String,
}

// ---------------------------------------------------------------------------
// PolicyRefinementEngine
// ---------------------------------------------------------------------------

/// Policy Refinement Engine — Mechanism 3 of the Chip de Memoria Adaptativa.
///
/// Classifies gray-area terms into canonical policy categories.
/// Uses a three-tier lookup strategy:
/// 1. Ontology base (built-in priority terms)
/// 2. Semantic graph (learned classifications)
/// 3. Heuristic keyword matching
pub struct PolicyRefinementEngine {
    /// Reference to the hypothesis manager.
    hypothesis_mgr: Option<HypothesisManager>,
}

impl PolicyRefinementEngine {
    /// Creates a new policy refinement engine.
    pub fn new() -> Self {
        Self {
            hypothesis_mgr: None,
        }
    }

    /// Sets the hypothesis manager reference.
    pub fn set_hypothesis_manager(&mut self, mgr: HypothesisManager) {
        self.hypothesis_mgr = Some(mgr);
    }

    /// Classifies a term into a policy category.
    ///
    /// Lookup strategy:
    /// 1. Check ontology base for priority mappings
    /// 2. Check semantic graph for learned classifications
    /// 3. Heuristic keyword matching
    pub fn classify(
        &mut self,
        term: &str,
        tenant_id: &str,
        ontology: &OntologyBase,
        graph: &SemanticGraph,
    ) -> Result<RefinementResult, MemoryError> {
        let term_lower = term.to_lowercase().trim().to_string();

        // Strategy 1: Ontology base lookup
        if let Some(mapping) = ontology.lookup(&term_lower, tenant_id) {
            if mapping.relation == "priority_level" || mapping.relation == "classifies_as" {
                let category = PolicyCategory::from_key(&mapping.destination);
                if category != PolicyCategory::Unclassified {
                    return Ok(RefinementResult {
                        original_term: term.to_string(),
                        category,
                        relation: mapping.relation.clone(),
                        confidence: 0.8,
                        source: "ontology".to_string(),
                    });
                }
            }
        }

        // Strategy 2: Semantic graph (learned classifications)
        match graph.lookup(&term_lower, tenant_id) {
            Ok(Some(mapping)) if mapping.approved => {
                let category = PolicyCategory::from_key(&mapping.destination);
                if category != PolicyCategory::Unclassified {
                    return Ok(RefinementResult {
                        original_term: term.to_string(),
                        category,
                        relation: mapping.relation.clone(),
                        confidence: (mapping.confidence as f64) / 100.0,
                        source: "sqlite".to_string(),
                    });
                }
            }
            _ => {}
        }

        // Strategy 3: Heuristic keyword matching
        if let Some(category) = self.heuristic_classify(&term_lower) {
            return Ok(RefinementResult {
                original_term: term.to_string(),
                category,
                relation: "heuristic_classify".to_string(),
                confidence: 0.5,
                source: "heuristic".to_string(),
            });
        }

        // No match — unclassified
        Ok(RefinementResult {
            original_term: term.to_string(),
            category: PolicyCategory::Unclassified,
            relation: String::new(),
            confidence: 0.0,
            source: "none".to_string(),
        })
    }

    /// Generates a Policy Refinement hypothesis for an unclassified term.
    pub fn generate_hypothesis(
        &mut self,
        term: &str,
        suggested_category: &str,
        context: &str,
    ) -> Result<Hypothesis, MemoryError> {
        if let Some(ref mut mgr) = self.hypothesis_mgr {
            mgr.generate_policy_refinement(term, suggested_category, context)?;
            Ok(mgr.pending().last().unwrap().clone())
        } else {
            Ok(Hypothesis::new(
                term,
                "classifies_as",
                suggested_category,
                LearningMechanism::PolicyRefinement,
                context,
                0.3,
            ))
        }
    }

    /// Heuristic classification based on keyword patterns.
    fn heuristic_classify(&self, term: &str) -> Option<PolicyCategory> {
        let critical_kw = ["urgente", "inmediato", "emergencia", "critico", "urgencia"];
        let risky_kw = ["eliminar", "borrar", "destruir", "cancelar", "riesgo"];
        let managerial_kw = ["aprobar", "autorizar", "firmar", "validar", "gerente"];
        let operational_kw = ["reparar", "arreglar", "mantener", "actualizar", "corregir"];

        for kw in &critical_kw {
            if term.contains(kw) {
                return Some(PolicyCategory::GastoCritico);
            }
        }

        for kw in &risky_kw {
            if term.contains(kw) {
                return Some(PolicyCategory::OperacionRiesgosa);
            }
        }

        for kw in &managerial_kw {
            if term.contains(kw) {
                return Some(PolicyCategory::AccionGerencial);
            }
        }

        for kw in &operational_kw {
            if term.contains(kw) {
                return Some(PolicyCategory::GastoOperativo);
            }
        }

        None
    }
}

impl Default for PolicyRefinementEngine {
    fn default() -> Self {
        Self::new()
    }
}
