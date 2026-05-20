//! Error types for the Adaptive Binary Memory Chip.

use thiserror::Error;

/// Errors that can occur during memory chip operations.
#[derive(Debug, Error)]
pub enum MemoryError {
    // -- SQLite / Graph errors --
    /// SQLite database error.
    #[error("database error: {0}")]
    Database(String),

    /// A semantic mapping was not found in the graph.
    #[error("mapping not found: {0}")]
    NotFound(String),

    /// Legacy alias for `NotFound`.
    #[error("mapping not found: {0}")]
    MappingNotFound(String),

    /// Duplicate mapping insertion.
    #[error("duplicate mapping: {0}")]
    Duplicate(String),

    // -- Cache errors --
    /// Cache is full and cannot accept new entries.
    #[error("cache full: max size {0} reached")]
    CacheFull(usize),

    /// A cache miss or cache corruption error.
    #[error("cache error: {0}")]
    CacheError(String),

    // -- rkyv errors --
    /// rkyv serialization failure.
    #[error("rkyv serialization error: {0}")]
    RkyvSerialization(String),

    /// rkyv deserialization / validation failure.
    #[error("rkyv validation error: {0}")]
    RkyvValidation(String),

    // -- Feature gating --
    /// Feature gate blocked the operation.
    #[error("feature gated: {0}")]
    FeatureGated(String),

    /// Subscription gate denied the operation.
    #[error("subscription gate denied: {0}")]
    SubscriptionDenied(String),

    // -- Ontology errors --
    /// Ontology loading error.
    #[error("ontology error: {0}")]
    Ontology(String),

    // -- Learning lifecycle errors --
    /// The proposed operation was rejected by the LLM verdict layer.
    #[error("verdict rejected for mapping: {0}")]
    VerdictRejected(String),

    /// A human approval is required before this operation can proceed.
    #[error("human approval required: {0}")]
    ApprovalRequired(String),

    // -- Graph integrity --
    /// The semantic graph contains a cycle or invalid structure.
    #[error("graph integrity error: {0}")]
    GraphIntegrity(String),

    // -- Storage / Schema --
    /// SQLite storage backend error.
    #[error("storage error: {0}")]
    StorageError(String),

    /// Schema drift detected — the graph schema has diverged.
    #[error("schema drift detected: {0}")]
    SchemaDrift(String),

    /// Serialization or deserialization failure.
    #[error("serialization error: {0}")]
    SerializationError(String),

    /// Merkle seal verification failed — data integrity compromised.
    #[error("merkle seal verification failed: {0}")]
    MerkleSealFailed(String),

    // -- Policy --
    /// A policy refinement cycle exceeded the maximum iterations.
    #[error("policy refinement exceeded max iterations")]
    PolicyRefinementExceeded,

    // -- Hypothesis --
    /// A hypothesis failed or was rejected.
    #[error("hypothesis failed: {0}")]
    HypothesisFailed(String),

    // -- Serialization --
    /// Bincode serialization/deserialization failure.
    #[error("bincode serialization error: {0}")]
    BincodeSerialization(String),

    // -- HITL Validation (GRIETA 3) --
    /// Admin must review evidence before approval.
    #[error("admin evidence review is required")]
    EvidenceReviewRequired,

    /// Admin justification is too short (minimum 50 characters).
    #[error("justification too short: provided {provided} chars, required {required}")]
    JustificationTooShort { provided: usize, required: usize },

    /// Admin must acknowledge risk before approval.
    #[error("risk acknowledgment is required")]
    RiskAcknowledgmentRequired,

    /// Admin session ID is required.
    #[error("admin session ID is required")]
    SessionIdRequired,

    // -- Subscription Tier Restrictions --
    /// The operation is blocked by the feature gate.
    #[error("feature gate blocked: {0}")]
    FeatureGateBlocked(String),

    /// The learning mechanism is not available for this subscription tier.
    #[error("tier restricted: {tier} does not allow mechanism {mechanism}")]
    TierRestricted { tier: String, mechanism: String },

    // -- Generic --
    /// Generic internal error.
    #[error("internal error: {0}")]
    Internal(String),
}

impl From<rusqlite::Error> for MemoryError {
    fn from(err: rusqlite::Error) -> Self {
        MemoryError::Database(err.to_string())
    }
}
