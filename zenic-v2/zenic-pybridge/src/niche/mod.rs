//! Niche Core Types — Rust-compiled niche definitions for Zenic-Agents.
//!
//! This module defines the core data types for the new niche architecture
//! where niches are compiled into Rust (not static YAML) and serve as
//! the foundation for dynamic YAML template generation.

pub mod enums;
pub mod schema;
pub mod definition;
pub mod api;

pub use enums::{NicheCategory, DataSensitivity, FieldRequirement, TemplateFieldType};
pub use schema::{TemplateFieldSchema, TemplateSection};
pub use definition::NicheDefinition;
pub use api::{get_niche_categories, get_niche_category_display_names};

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_niche_category_str_roundtrip() {
        assert_eq!(NicheCategory::AiData.as_str(), "ai_data");
        assert_eq!(NicheCategory::FinTech.as_str(), "fintech");
        assert_eq!(NicheCategory::HealthTech.as_str(), "healthtech");
        assert_eq!(NicheCategory::GreenTech.as_str(), "greentech");
        assert_eq!(NicheCategory::EdTech.as_str(), "edtech");
        assert_eq!(NicheCategory::PropTech.as_str(), "proptech");
        assert_eq!(NicheCategory::LegalTech.as_str(), "legaltech");
    }

    #[test]
    fn test_niche_category_display_names() {
        assert_eq!(NicheCategory::AiData.display_name(), "IA y Datos");
        assert_eq!(NicheCategory::FinTech.display_name(), "Tecnología Financiera");
        assert_eq!(NicheCategory::HealthTech.display_name(), "Tecnología de la Salud");
        assert_eq!(NicheCategory::GreenTech.display_name(), "Tecnología Verde");
        assert_eq!(NicheCategory::EdTech.display_name(), "Tecnología Educativa");
        assert_eq!(NicheCategory::PropTech.display_name(), "Tecnología Inmobiliaria");
        assert_eq!(NicheCategory::LegalTech.display_name(), "Tecnología Jurídica");
    }

    #[test]
    fn test_niche_category_all_count() {
        assert_eq!(NicheCategory::all().len(), 7);
    }

    #[test]
    fn test_data_sensitivity_str_roundtrip() {
        assert_eq!(DataSensitivity::Low.as_str(), "low");
        assert_eq!(DataSensitivity::Medium.as_str(), "medium");
        assert_eq!(DataSensitivity::High.as_str(), "high");
        assert_eq!(DataSensitivity::Critical.as_str(), "critical");
    }

    #[test]
    fn test_field_requirement_str_roundtrip() {
        assert_eq!(FieldRequirement::Required.as_str(), "required");
        assert_eq!(FieldRequirement::Optional.as_str(), "optional");
        assert_eq!(FieldRequirement::Conditional.as_str(), "conditional");
    }

    #[test]
    fn test_template_field_type_count() {
        // 14 field types
        let types = [
            TemplateFieldType::Text,
            TemplateFieldType::Number,
            TemplateFieldType::Boolean,
            TemplateFieldType::Date,
            TemplateFieldType::DateTime,
            TemplateFieldType::Email,
            TemplateFieldType::Url,
            TemplateFieldType::Phone,
            TemplateFieldType::Currency,
            TemplateFieldType::Percentage,
            TemplateFieldType::Json,
            TemplateFieldType::Enum,
            TemplateFieldType::Reference,
            TemplateFieldType::File,
        ];
        assert_eq!(types.len(), 14);
    }

    #[test]
    fn test_template_field_schema_creation() {
        let field = TemplateFieldSchema::new(
            "email".to_string(),
            "Email Address".to_string(),
            TemplateFieldType::Email,
            FieldRequirement::Required,
        );
        assert_eq!(field.name(), "email");
        assert_eq!(field.display_name(), "Email Address");
        assert!(field.is_required());
        assert!(!field.is_conditional());
    }

    #[test]
    fn test_template_section_creation() {
        let mut section = TemplateSection::new(
            "contact_info".to_string(),
            "Contact Information".to_string(),
        );
        let field = TemplateFieldSchema::new(
            "phone".to_string(),
            "Phone Number".to_string(),
            TemplateFieldType::Phone,
            FieldRequirement::Optional,
        );
        section.add_field(field);
        assert_eq!(section.section_id(), "contact_info");
        assert_eq!(section.field_count(), 1);
        assert_eq!(section.required_count(), 0);
    }

    #[test]
    fn test_niche_definition_creation() {
        let niche = NicheDefinition::new(
            "test_niche".to_string(),
            "Test Niche".to_string(),
            NicheCategory::AiData,
            "A test niche for unit testing".to_string(),
            "testing".to_string(),
            DataSensitivity::Low,
        );
        assert_eq!(niche.niche_id(), "test_niche");
        assert_eq!(niche.category(), NicheCategory::AiData);
        assert_eq!(niche.data_sensitivity(), DataSensitivity::Low);
        assert_eq!(niche.total_fields(), 0);
        assert_eq!(niche.required_fields(), 0);
    }

    #[test]
    fn test_niche_definition_with_sections() {
        let mut niche = NicheDefinition::new(
            "ai_automation".to_string(),
            "Automatización IA".to_string(),
            NicheCategory::AiData,
            "AI automation platform".to_string(),
            "ai".to_string(),
            DataSensitivity::High,
        );
        let mut section = TemplateSection::new(
            "model_config".to_string(),
            "Model Configuration".to_string(),
        );
        section.add_field(TemplateFieldSchema::new(
            "model_name".to_string(),
            "Model Name".to_string(),
            TemplateFieldType::Text,
            FieldRequirement::Required,
        ));
        section.add_field(TemplateFieldSchema::new(
            "temperature".to_string(),
            "Temperature".to_string(),
            TemplateFieldType::Number,
            FieldRequirement::Optional,
        ));
        niche.add_section(section);
        assert_eq!(niche.total_fields(), 2);
        assert_eq!(niche.required_fields(), 1);
    }

    #[test]
    fn test_template_field_schema_empty_name() {
        // Should not panic, just log error
        let field = TemplateFieldSchema::new(
            "  ".to_string(),
            "Empty".to_string(),
            TemplateFieldType::Text,
            FieldRequirement::Required,
        );
        // Name is trimmed
        assert_eq!(field.name(), "");
    }

    #[test]
    fn test_niche_definition_compliance_check() {
        let mut niche = NicheDefinition::new(
            "health_niche".to_string(),
            "Health Niche".to_string(),
            NicheCategory::HealthTech,
            "Health platform".to_string(),
            "health".to_string(),
            DataSensitivity::Critical,
        );
        niche.set_compliance(vec!["HIPAA".to_string(), "GDPR".to_string()]);
        assert!(niche.has_compliance("HIPAA"));
        assert!(niche.has_compliance("hipaa"));
        assert!(niche.has_compliance("GDPR"));
        assert!(!niche.has_compliance("PCI"));
    }
}
