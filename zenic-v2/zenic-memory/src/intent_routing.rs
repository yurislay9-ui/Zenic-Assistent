//! Intent Routing — Mechanism 2 [T1-5, T1-8]
//!
//! Routes ambiguous user intents to the correct MCP tool.
//! Example: "tumba la cuenta" → cancelar_suscripcion
//!
//! When the DeterministicPipeline cannot confidently route a user
//! command to an MCP executor, the IntentRouter generates a hypothesis
//! that maps the colloquial expression to the canonical tool name.

use crate::errors::MemoryError;
use crate::graph::SemanticGraph;
use crate::hypothesis::HypothesisManager;
use crate::ontology::OntologyBase;
use crate::types::{Hypothesis, LearningMechanism};

// ---------------------------------------------------------------------------
// IntentMatch
// ---------------------------------------------------------------------------

/// Result of an intent routing lookup.
#[derive(Debug, Clone)]
pub struct IntentMatch {
    /// The original user expression.
    pub user_intent: String,
    /// The matched MCP tool name.
    pub mcp_tool: String,
    /// The relation type that connected them.
    pub relation: String,
    /// Confidence of the match (0.0–1.0).
    pub confidence: f64,
    /// Source of the match ("cache", "ontology", "sqlite", "none").
    pub source: String,
}

// ---------------------------------------------------------------------------
// IntentRouter
// ---------------------------------------------------------------------------

/// Intent Router — Mechanism 2 of the Chip de Memoria Adaptativa.
///
/// Maps colloquial or ambiguous user expressions to canonical MCP tool names.
/// Uses a three-tier lookup strategy:
/// 1. Exact match in LRU cache (<1μs)
/// 2. Ontology base lookup (~50 built-in action mappings)
/// 3. SQLite semantic graph lookup (<2ms)
///
/// If none match, generates a hypothesis for the learning flow.
pub struct IntentRouter {
    /// Known MCP tools available for routing.
    mcp_tools: Vec<String>,
    /// Reference to the hypothesis manager.
    hypothesis_mgr: Option<HypothesisManager>,
}

impl IntentRouter {
    /// Creates a new intent router with the given MCP tools.
    pub fn new(mcp_tools: Vec<String>) -> Self {
        Self {
            mcp_tools,
            hypothesis_mgr: None,
        }
    }

    /// Creates an intent router with common business MCP tools.
    pub fn with_default_tools() -> Self {
        Self::new(vec![
            "cancelar_suscripcion".to_string(),
            "activar_suscripcion".to_string(),
            "desactivar_suscripcion".to_string(),
            "crear_factura".to_string(),
            "eliminar_registro".to_string(),
            "modificar_registro".to_string(),
            "verificar_estado".to_string(),
            "enviar_notificacion".to_string(),
            "generar_reporte".to_string(),
            "procesar_pago".to_string(),
            "consultar_inventario".to_string(),
            "actualizar_cliente".to_string(),
            "reparar_servicio".to_string(),
            "agregar_producto".to_string(),
            "remover_producto".to_string(),
        ])
    }

    /// Sets the hypothesis manager reference.
    pub fn set_hypothesis_manager(&mut self, mgr: HypothesisManager) {
        self.hypothesis_mgr = Some(mgr);
    }

    /// Routes a user intent to an MCP tool.
    ///
    /// Lookup strategy:
    /// 1. Check ontology base for known action mappings
    /// 2. Check semantic graph for learned mappings
    /// 3. If no match, generate a hypothesis
    pub fn route(
        &mut self,
        user_intent: &str,
        tenant_id: &str,
        ontology: &OntologyBase,
        graph: &SemanticGraph,
    ) -> Result<IntentMatch, MemoryError> {
        let intent_lower = user_intent.to_lowercase().trim().to_string();

        // Strategy 1: Check ontology base
        if let Some(mapping) = ontology.lookup(&intent_lower, tenant_id) {
            if mapping.relation == "action_for" || mapping.relation == "routes_to" {
                return Ok(IntentMatch {
                    user_intent: user_intent.to_string(),
                    mcp_tool: mapping.destination.clone(),
                    relation: mapping.relation.clone(),
                    confidence: 0.8,
                    source: "ontology".to_string(),
                });
            }
        }

        // Strategy 2: Check semantic graph (learned mappings)
        match graph.lookup(&intent_lower, tenant_id) {
            Ok(Some(mapping)) if mapping.approved => {
                return Ok(IntentMatch {
                    user_intent: user_intent.to_string(),
                    mcp_tool: mapping.destination.clone(),
                    relation: mapping.relation.clone(),
                    confidence: (mapping.confidence as f64) / 100.0,
                    source: "sqlite".to_string(),
                });
            }
            Ok(Some(mapping)) => {
                // Mapping exists but not yet approved
                return Ok(IntentMatch {
                    user_intent: user_intent.to_string(),
                    mcp_tool: mapping.destination.clone(),
                    relation: mapping.relation.clone(),
                    confidence: 0.3,
                    source: "sqlite_unapproved".to_string(),
                });
            }
            _ => {}
        }

        // Strategy 3: Heuristic matching against MCP tool names
        if let Some(tool) = self.heuristic_match(&intent_lower) {
            return Ok(IntentMatch {
                user_intent: user_intent.to_string(),
                mcp_tool: tool,
                relation: "heuristic_match".to_string(),
                confidence: 0.5,
                source: "heuristic".to_string(),
            });
        }

        // No match found — return with no tool
        Ok(IntentMatch {
            user_intent: user_intent.to_string(),
            mcp_tool: String::new(),
            relation: String::new(),
            confidence: 0.0,
            source: "none".to_string(),
        })
    }

    /// Generates an Intent Routing hypothesis for a failed routing.
    pub fn generate_hypothesis(
        &mut self,
        user_intent: &str,
        suggested_tool: &str,
        context: &str,
    ) -> Result<Hypothesis, MemoryError> {
        if let Some(ref mut mgr) = self.hypothesis_mgr {
            mgr.generate_intent_routing(user_intent, suggested_tool, context)?;
            Ok(mgr.pending().last().unwrap().clone())
        } else {
            Ok(Hypothesis::new(
                user_intent,
                "routes_to",
                suggested_tool,
                LearningMechanism::IntentRouting,
                context,
                0.4,
            ))
        }
    }

    /// Heuristic matching: try to find the closest MCP tool by keyword overlap.
    fn heuristic_match(&self, intent: &str) -> Option<String> {
        let intent_words: Vec<&str> = intent.split_whitespace().collect();

        for tool in &self.mcp_tools {
            let tool_words: Vec<&str> = tool.split('_').collect();
            // Check if any intent word matches any tool word
            for iw in &intent_words {
                for tw in &tool_words {
                    if iw.starts_with(tw) || tw.starts_with(iw) {
                        return Some(tool.clone());
                    }
                }
            }
        }

        None
    }

    /// Returns the list of available MCP tools.
    pub fn mcp_tools(&self) -> &[String] {
        &self.mcp_tools
    }

    /// Adds a new MCP tool.
    pub fn add_tool(&mut self, tool: String) {
        if !self.mcp_tools.contains(&tool) {
            self.mcp_tools.push(tool);
        }
    }
}
