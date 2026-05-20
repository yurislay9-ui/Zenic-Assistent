//! Niche Catalog — Static compiled catalog of 24 cutting-edge niches.
//!
//! All niche definitions are compiled into the Rust binary at build time.
//! No YAML loading, no filesystem access, no runtime parsing. This
//! guarantees deterministic behavior and eliminates the GAP-1 blocker
//! (empty zenic-ffi) identified in the analysis.
//!
//! # Catalog Structure
//!
//! 7 categories, 24 niches total:
//!
//! | Category   | Count | Niches                                      |
//! |------------|-------|---------------------------------------------|
//! | IA y Datos | 4     | ai_automation, data_analytics, ml_operations, nlp_services |
//! | Tecnología Financiera | 4     | defi_protocols, neo_banking, insurtech, regtech |
//! | Tecnología de la Salud | 4     | telemedicine, mental_health_ai, genomics, wearables_health |
//! | Tecnología Verde | 3     | carbon_tracking, smart_grid, circular_economy |
//! | Tecnología Educativa | 3     | adaptive_learning, vr_education, micro_credentials |
//! | Tecnología Inmobiliaria | 3     | smart_buildings, digital_twins, fractional_ownership |
//! | Tecnología Jurídica | 3     | smart_contracts, legal_ai, compliance_automation |
//!
//! # PyO3 Functions
//!
//! - `catalog_get_all()` — list all NicheDefinitions
//! - `catalog_get_by_id(niche_id)` — lookup by niche_id
//! - `catalog_get_by_category(category)` — filter by category
//! - `catalog_search(query)` — search by name, domain, tags
//! - `catalog_count()` — total niches in catalog
//! - `catalog_ids()` — list all niche_id strings

mod catalog_data;
mod niches_ai_health;
mod niches_green_legal;
mod sections;

#[cfg(test)]
mod tests;

// Re-export all public catalog functions so they remain accessible as crate::catalog::*
pub use catalog_data::{
    catalog_count, catalog_get_all, catalog_get_by_category, catalog_get_by_id, catalog_ids,
    catalog_search,
};
