//! Template unit tests.

#[cfg(test)]
mod tests {
    use super::*;
    use crate::niche::{DataSensitivity, FieldRequirement, NicheCategory,
                       NicheDefinition, TemplateFieldType};

    #[test]
    fn test_catalog_lookup_for_template() {
        // Verify catalog has the niches that template_generate depends on
        let niche = crate::catalog::catalog_get_by_id("telemedicine");
        assert!(niche.is_some());
        assert_eq!(niche.unwrap().niche_id(), "telemedicine");
    }

    #[test]
    fn test_catalog_lookup_returns_none_for_invalid() {
        let niche = crate::catalog::catalog_get_by_id("nonexistent_niche");
        assert!(niche.is_none());
    }

    #[test]
    fn test_niche_definition_field_counts() {
        let niche = crate::catalog::catalog_get_by_id("ai_automation").unwrap();
        assert!(niche.total_field_count() > 0);
        assert!(niche.required_field_count() > 0);
        assert!(niche.required_field_count() <= niche.total_field_count());
    }

    #[test]
    fn test_all_niches_have_sections_for_template() {
        let ids = crate::catalog::catalog_ids();
        for id in ids {
            let niche = crate::catalog::catalog_get_by_id(&id).unwrap();
            assert!(
                niche.section_count() >= 2,
                "Niche {} should have at least 2 sections, got {}",
                id,
                niche.section_count(),
            );
        }
    }

    #[test]
    fn test_template_field_type_completeness() {
        // Verify all field types have valid as_str representations
        assert_eq!(TemplateFieldType::Text.as_str(), "text");
        assert_eq!(TemplateFieldType::Number.as_str(), "number");
        assert_eq!(TemplateFieldType::Boolean.as_str(), "boolean");
        assert_eq!(TemplateFieldType::Date.as_str(), "date");
        assert_eq!(TemplateFieldType::DateTime.as_str(), "datetime");
        assert_eq!(TemplateFieldType::Email.as_str(), "email");
        assert_eq!(TemplateFieldType::Url.as_str(), "url");
        assert_eq!(TemplateFieldType::Phone.as_str(), "phone");
        assert_eq!(TemplateFieldType::Currency.as_str(), "currency");
        assert_eq!(TemplateFieldType::Percentage.as_str(), "percentage");
        assert_eq!(TemplateFieldType::Json.as_str(), "json");
        assert_eq!(TemplateFieldType::Enum.as_str(), "enum");
        assert_eq!(TemplateFieldType::Reference.as_str(), "reference");
        assert_eq!(TemplateFieldType::File.as_str(), "file");
    }

    #[test]
    fn test_field_requirement_values() {
        assert_eq!(FieldRequirement::Required.as_str(), "required");
        assert_eq!(FieldRequirement::Optional.as_str(), "optional");
        assert_eq!(FieldRequirement::Conditional.as_str(), "conditional");
    }
}
