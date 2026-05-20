//! Learning-related types: LearningMechanism, SemanticMapping, Hypothesis, LearningVerdict.

use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// LearningMechanism — The 3 Learning Mechanisms [T1]
// ---------------------------------------------------------------------------

/// The mechanism by which a semantic mapping was learned.
///
/// Each mechanism corresponds to a specific learning pattern:
/// - **SchemaDrift** — DB column renames: "estatus_cliente → estado_id" [T1-4,T1-7]
/// - **IntentRouting** — MCP tool matching: "tumba la cuenta → cancelar_suscripcion" [T1-5,T1-8]
/// - **PolicyRefinement** — Gray-area classification: "reparación urgente → gasto_crítico" [T1-6,T1-9]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LearningMechanism {
    /// Mechanism 1: Schema Drift — DB column renames and field adaptations.
    SchemaDrift,
    /// Mechanism 2: Intent Routing — Ambiguous user intent → MCP tool matching.
    IntentRouting,
    /// Mechanism 3: Policy Refinement — Gray-area security/business policy classification.
    PolicyRefinement,
    /// Built-in ontology mapping (not learned, pre-defined).
    OntologyBase,
}

impl LearningMechanism {
    /// Returns the string representation used in SQLite storage.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::SchemaDrift => "schema_drift",
            Self::IntentRouting => "intent_routing",
            Self::PolicyRefinement => "policy_refinement",
            Self::OntologyBase => "ontology_base",
        }
    }

    /// Parses a mechanism from its string representation.
    pub fn from_str_lossy(s: &str) -> Self {
        match s {
            "schema_drift" => Self::SchemaDrift,
            "intent_routing" => Self::IntentRouting,
            "policy_refinement" => Self::PolicyRefinement,
            "ontology_base" => Self::OntologyBase,
            _ => Self::OntologyBase,
        }
    }

    /// Returns all learning mechanisms (excluding OntologyBase).
    pub fn learnable() -> &'static [LearningMechanism] {
        &[Self::SchemaDrift, Self::IntentRouting, Self::PolicyRefinement]
    }
}

impl std::fmt::Display for LearningMechanism {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

// ---------------------------------------------------------------------------
// SemanticMapping — Deterministic Knowledge Graph Record [T1-2, T1-3]
// ---------------------------------------------------------------------------

/// A single semantic mapping in the knowledge graph.
///
/// Represents a directed relationship: `origin --[relation]--> destination`.
/// Each mapping is isolated per tenant and tracks confidence, approval status,
/// and optional Merkle hash for integrity verification.
///
/// Example: "cobro" → "synonym_of" → "factura"
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct SemanticMapping {
    /// Unique identifier (UUID v4 string).
    pub mapping_id: String,
    /// The source term / concept (e.g., "cobro").
    pub origin: String,
    /// The relationship type (e.g., "synonym_of", "action_for", "maps_to").
    pub relation: String,
    /// The target term / concept (e.g., "factura").
    pub destination: String,
    /// How this mapping was learned.
    pub mechanism: LearningMechanism,
    /// Confidence score (0–100). Set after HITL approval.
    pub confidence: u8,
    /// Tenant isolation key. `"__anonymous__"` for unauthenticated,
    /// `"__ontology_base__"` for built-in ontology mappings.
    pub tenant_id: String,
    /// Unix epoch milliseconds when this mapping was created.
    pub created_at: i64,
    /// Whether this mapping has been approved by HITL.
    pub approved: bool,
    /// BLAKE3 Merkle hash seal after approval.
    pub merkle_hash: Option<String>,
}

impl SemanticMapping {
    /// Creates a new unapproved semantic mapping.
    pub fn new(
        mapping_id: String,
        origin: String,
        relation: String,
        destination: String,
        mechanism: LearningMechanism,
    ) -> Self {
        Self {
            mapping_id,
            origin,
            relation,
            destination,
            mechanism,
            confidence: 0,
            tenant_id: "__anonymous__".to_string(),
            created_at: now_millis(),
            approved: false,
            merkle_hash: None,
        }
    }

    /// Creates an ontology-base mapping with standard defaults.
    pub fn ontology_base(
        mapping_id: String,
        origin: String,
        relation: String,
        destination: String,
    ) -> Self {
        Self {
            mapping_id,
            origin,
            relation,
            destination,
            mechanism: LearningMechanism::OntologyBase,
            confidence: 80,
            tenant_id: "__ontology_base__".to_string(),
            created_at: 0,
            approved: true,
            merkle_hash: None,
        }
    }

    /// Generates the binary question for IA classification.
    /// The LLM only answers YES/NO — never generates content.
    pub fn binary_question(&self) -> String {
        format!(
            "¿Es correcto mapear '{}' como {} de '{}'?",
            self.origin, self.relation, self.destination
        )
    }

    /// Creates a cache key for this mapping.
    pub fn cache_key(&self) -> String {
        format!("{}::{}", self.tenant_id, self.origin)
    }
}

// ---------------------------------------------------------------------------
// Hypothesis — Pre-IA Proposal [T1]
// ---------------------------------------------------------------------------

/// A hypothesis generated by the deterministic layer for IA classification.
///
/// "La Capa Estructurada Propone, la IA Clasifica SÍ/NO, el Humano Valida."
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Hypothesis {
    /// The origin term that triggered the hypothesis.
    pub origin: String,
    /// Proposed relation type.
    pub proposed_relation: String,
    /// Proposed destination term.
    pub proposed_destination: String,
    /// Which mechanism generated this hypothesis.
    pub mechanism: LearningMechanism,
    /// Why this hypothesis was generated (context).
    pub context: String,
    /// Deterministic confidence before IA classification.
    pub confidence_before_ia: f64,
    /// The binary YES/NO question for the IA.
    pub binary_question: String,
}

impl Hypothesis {
    /// Creates a new hypothesis.
    pub fn new(
        origin: impl Into<String>,
        proposed_relation: impl Into<String>,
        proposed_destination: impl Into<String>,
        mechanism: LearningMechanism,
        context: impl Into<String>,
        confidence_before_ia: f64,
    ) -> Self {
        let origin = origin.into();
        let proposed_relation = proposed_relation.into();
        let proposed_destination = proposed_destination.into();
        let binary_question = format!(
            "¿Es correcto mapear '{}' como {} de '{}'?",
            origin, proposed_relation, proposed_destination
        );
        Self {
            origin,
            proposed_relation,
            proposed_destination,
            mechanism,
            context: context.into(),
            confidence_before_ia,
            binary_question,
        }
    }

    /// Converts this hypothesis into a SemanticMapping (pending approval).
    pub fn to_mapping(&self, tenant_id: &str) -> SemanticMapping {
        SemanticMapping {
            mapping_id: uuid::Uuid::new_v4().to_string(),
            origin: self.origin.clone(),
            relation: self.proposed_relation.clone(),
            destination: self.proposed_destination.clone(),
            mechanism: self.mechanism,
            confidence: (self.confidence_before_ia * 100.0) as u8,
            tenant_id: tenant_id.to_string(),
            created_at: now_millis(),
            approved: false,
            merkle_hash: None,
        }
    }
}

// ---------------------------------------------------------------------------
// LearningVerdict — 4-Layer Verdict Result [T2]
// ---------------------------------------------------------------------------

/// Result from the 4-layer verdict pipeline.
///
/// Wraps the mapping with IA classification results and evidence.
/// The LLM NEVER generates content — only emits boolean verdict.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LearningVerdict {
    /// The mapping being evaluated.
    pub mapping: SemanticMapping,
    /// The exact binary question asked to the IA.
    pub ia_question: String,
    /// IA response: true = YES (accept mapping), false = NO (reject).
    pub ia_response: bool,
    /// Evidence in favor (from Layer 2: EvidenceCollector).
    pub evidence_for: Vec<String>,
    /// Evidence against (from Layer 2: EvidenceCollector).
    pub evidence_against: Vec<String>,
    /// Consensus score from Layer 3 (ConsensusResolver).
    pub consensus_score: f64,
    /// Which layer resolved the verdict (1-4).
    pub layer_resolved: u8,
}

impl LearningVerdict {
    /// Creates a Layer 1 (deterministic) bypass verdict — no IA needed.
    pub fn deterministic_accept(mapping: SemanticMapping) -> Self {
        let question = mapping.binary_question();
        Self {
            mapping,
            ia_question: question,
            ia_response: true,
            evidence_for: vec!["deterministic_match".to_string()],
            evidence_against: vec![],
            consensus_score: 1.0,
            layer_resolved: 1,
        }
    }

    /// Creates a Layer 4 (IA) verdict.
    pub fn ia_verdict(
        mapping: SemanticMapping,
        ia_response: bool,
        evidence_for: Vec<String>,
        evidence_against: Vec<String>,
        consensus_score: f64,
    ) -> Self {
        let question = mapping.binary_question();
        Self {
            mapping,
            ia_question: question,
            ia_response,
            evidence_for,
            evidence_against,
            consensus_score,
            layer_resolved: 4,
        }
    }

    /// Returns true if resolved at Layer 1 (deterministic, no IA).
    pub fn is_deterministic(&self) -> bool {
        self.layer_resolved == 1
    }
}

/// Returns current Unix epoch in milliseconds.
pub(crate) fn now_millis() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as i64
}
