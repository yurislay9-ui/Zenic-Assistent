//! Template types and schema documentation.
//!
//! This module documents the YAML template structure used throughout
//! the template subsystem. The actual Rust types are NicheDefinition,
//! TemplateFieldSchema, etc. (from [`crate::niche`]), while the
//! generated templates are Python dicts with the structure described
//! below.
//!
//! # Template Structure
//!
//! A generated YAML template has this structure:
//!
//! ```yaml
//! template:
//!   metadata:
//!     niche_id: "telemedicine"
//!     niche_name: "Telemedicina"
//!     version: "1.0.0"
//!     generated_at: "2025-01-15T10:30:00Z"
//!     status: "incomplete"
//!   sections:
//!     business_identity:
//!       _title: "Business Identity"
//!       _description: "Core business identification and branding."
//!       business_name:
//!         _type: text
//!         _display: "Business Name"
//!         _required: true
//!         value: null
//!       ...
//!   completeness:
//!     total_fields: 45
//!     filled_fields: 0
//!     missing_required: 30
//!     completion_pct: 0.0
//! ```

// Re-export niche types that template submodules rely on, so they can
// `use super::types::NicheDefinition` instead of reaching into `crate::niche`.
pub(crate) use crate::niche::{FieldRequirement, NicheDefinition, TemplateFieldType};
