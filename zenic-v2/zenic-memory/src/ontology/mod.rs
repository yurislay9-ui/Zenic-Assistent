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

mod types;
mod builtin;

// Re-export all public types.
pub use types::OntologyBase;
