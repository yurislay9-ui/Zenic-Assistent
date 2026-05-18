// ─── Niche Enums ────────────────────────────────────────────────────────
// NicheCategory, DataSensitivity, FieldRequirement, TemplateFieldType

use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════
//  NicheCategory — 7 cutting-edge industry categories
// ═══════════════════════════════════════════════════════════════

/// Industry category for a niche.
///
/// Each category groups related niches that share compliance
/// requirements, data sensitivity patterns, and workflow structures.
#[pyclass(name = "NicheCategory", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum NicheCategory {
    AiData,
    FinTech,
    HealthTech,
    GreenTech,
    EdTech,
    PropTech,
    LegalTech,
}

impl NicheCategory {
    /// Return the Python-enum string value.
    pub fn as_str(&self) -> &'static str {
        match self {
            NicheCategory::AiData => "ai_data",
            NicheCategory::FinTech => "fintech",
            NicheCategory::HealthTech => "healthtech",
            NicheCategory::GreenTech => "greentech",
            NicheCategory::EdTech => "edtech",
            NicheCategory::PropTech => "proptech",
            NicheCategory::LegalTech => "legaltech",
        }
    }

    /// Human-readable display name (Spanish).
    pub fn display_name(&self) -> &'static str {
        match self {
            NicheCategory::AiData => "IA y Datos",
            NicheCategory::FinTech => "Tecnología Financiera",
            NicheCategory::HealthTech => "Tecnología de la Salud",
            NicheCategory::GreenTech => "Tecnología Verde",
            NicheCategory::EdTech => "Tecnología Educativa",
            NicheCategory::PropTech => "Tecnología Inmobiliaria",
            NicheCategory::LegalTech => "Tecnología Jurídica",
        }
    }

    /// All variants in catalog order.
    pub fn all() -> &'static [NicheCategory] {
        &[
            NicheCategory::AiData,
            NicheCategory::FinTech,
            NicheCategory::HealthTech,
            NicheCategory::GreenTech,
            NicheCategory::EdTech,
            NicheCategory::PropTech,
            NicheCategory::LegalTech,
        ]
    }
}

#[pymethods]
impl NicheCategory {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("NicheCategory.{}", self.display_name().replace(' ', ""))
    }
}

// ═══════════════════════════════════════════════════════════════
//  DataSensitivity — 4 sensitivity levels
// ═══════════════════════════════════════════════════════════════

/// Data sensitivity classification for a niche.
#[pyclass(name = "DataSensitivity", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum DataSensitivity {
    Low,
    Medium,
    High,
    Critical,
}

impl DataSensitivity {
    pub fn as_str(&self) -> &'static str {
        match self {
            DataSensitivity::Low => "low",
            DataSensitivity::Medium => "medium",
            DataSensitivity::High => "high",
            DataSensitivity::Critical => "critical",
        }
    }
}

#[pymethods]
impl DataSensitivity {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("DataSensitivity.{}", self.as_str().to_uppercase())
    }
}

// ═══════════════════════════════════════════════════════════════
//  FieldRequirement — field requirement classification
// ═══════════════════════════════════════════════════════════════

/// Whether a template field is required, optional, or conditional.
#[pyclass(name = "FieldRequirement", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum FieldRequirement {
    Required,
    Optional,
    Conditional,
}

impl FieldRequirement {
    pub fn as_str(&self) -> &'static str {
        match self {
            FieldRequirement::Required => "required",
            FieldRequirement::Optional => "optional",
            FieldRequirement::Conditional => "conditional",
        }
    }
}

#[pymethods]
impl FieldRequirement {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("FieldRequirement.{}", self.as_str().to_uppercase())
    }
}

// ═══════════════════════════════════════════════════════════════
//  TemplateFieldType — 14 field types for template schemas
// ═══════════════════════════════════════════════════════════════

/// Type of a template field, controlling validation and UI rendering.
#[pyclass(name = "TemplateFieldType", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum TemplateFieldType {
    Text,
    Number,
    Boolean,
    Date,
    DateTime,
    Email,
    Url,
    Phone,
    Currency,
    Percentage,
    Json,
    Enum,
    Reference,
    File,
}

impl TemplateFieldType {
    pub fn as_str(&self) -> &'static str {
        match self {
            TemplateFieldType::Text => "text",
            TemplateFieldType::Number => "number",
            TemplateFieldType::Boolean => "boolean",
            TemplateFieldType::Date => "date",
            TemplateFieldType::DateTime => "datetime",
            TemplateFieldType::Email => "email",
            TemplateFieldType::Url => "url",
            TemplateFieldType::Phone => "phone",
            TemplateFieldType::Currency => "currency",
            TemplateFieldType::Percentage => "percentage",
            TemplateFieldType::Json => "json",
            TemplateFieldType::Enum => "enum",
            TemplateFieldType::Reference => "reference",
            TemplateFieldType::File => "file",
        }
    }
}

#[pymethods]
impl TemplateFieldType {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("TemplateFieldType.{}", self.as_str().to_uppercase())
    }
}
