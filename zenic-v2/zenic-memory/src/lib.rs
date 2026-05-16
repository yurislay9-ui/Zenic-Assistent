//! # zenic-memory
//!
//! Semantic memory layer for Zenic-Agents: deterministic knowledge graph,
//! LRU cache with rkyv zero-copy, and shared ontology.
//!
//! This crate provides:
//! - [`SemanticGraph`] — SQLite-backed deterministic knowledge graph with
//!   per-tenant isolation, approval workflows, and audit logging.
//! - [`MemoryCache`] — LRU memory cache for hot-path lookups (<1μs) with
//!   rkyv pre-serialized entries for zero-copy reads.
//! - [`OntologyBase`] — Shared ontology layer with ~50 built-in Spanish
//!   business term mappings and opt-in per-tenant overrides.
//! - [`DagAdapter`] — Bridges the semantic graph to the Zenic fractal DAG.
//! - [`HypothesisManager`] — Manages learning hypotheses awaiting classification.
//! - [`IntentRouter`] — Routes user intents to semantic sub-graphs.
//! - [`PolicyRefinementEngine`] — Iteratively refines Policy Engine rules.
//! - [`SchemaDriftDetector`] — Monitors for structural schema drift.
//! - [`VerdictAdapter`] — Translates LLM boolean verdicts into memory actions.
//! - [`HitlBridge`] — Connects the Memory Chip to human validation.
//! - [`MerkleSeal`] — Cryptographic integrity verification via BLAKE3.
//! - [`YamlRenderer`] — Serializes graph state to human-readable YAML.
//! - [`SubscriptionGate`] — Enforces subscription-based access controls.
//! - [`LifecycleManager`] — Manages the full learning lifecycle.
//!
//! ## Architecture
//!
//! ```text
//! ┌─────────────┐     ┌──────────────┐     ┌───────────────┐
//! │ OntologyBase │────>│ MemoryCache  │────>│ SemanticGraph │
//! │ (built-in)   │     │ (hot path)   │     │ (SQLite)      │
//! └─────────────┘     └──────────────┘     └───────────────┘
//!        │                    │                     │
//!   base mappings       <1μs lookup          persistent store
//!   tenant overrides    rkyv zero-copy       audit + merkle
//! ```

pub mod cache;
pub mod dag_adapter;
pub mod errors;
pub mod graph;
pub mod hitl_bridge;
pub mod hypothesis;
pub mod intent_routing;
pub mod lifecycle;
pub mod merkle_seal;
pub mod ontology;
pub mod policy_refinement;
pub mod schema_drift;
pub mod subscription_gate;
pub mod types;
pub mod verdict_adapter;
pub mod yaml_renderer;

// Convenience re-exports.
pub use cache::MemoryCache;
pub use dag_adapter::DagAdapter;
pub use errors::MemoryError;
pub use graph::SemanticGraph;
pub use hitl_bridge::HitlBridge;
pub use hypothesis::HypothesisManager;
pub use intent_routing::IntentRouter;
pub use lifecycle::LifecycleManager;
pub use merkle_seal::MerkleSeal;
pub use ontology::OntologyBase;
pub use policy_refinement::PolicyRefinementEngine;
pub use schema_drift::SchemaDriftDetector;
pub use subscription_gate::SubscriptionGate;
pub use types::{FeatureGate, LearningMechanism, LearningVerdict, MemoryApprovalRequest, NodeValue, SemanticMapping, SubscriptionTier};
pub use verdict_adapter::VerdictAdapter;
pub use yaml_renderer::YamlRenderer;
