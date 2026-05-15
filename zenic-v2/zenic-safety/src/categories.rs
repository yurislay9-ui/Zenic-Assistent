//! Niche categories for domain-specific safety rules.
//!
//! 7 categories matching the niche catalog, each with 5 domain-specific rules.

use serde::{Deserialize, Serialize};
use std::fmt;

// ---------------------------------------------------------------------------
// NicheCategory
// ---------------------------------------------------------------------------

/// Niche domain categories for domain-specific safety rules.
///
/// Each category has 5 dedicated safety rules and a set of compliance
/// standards that must be validated.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum NicheCategory {
    /// IA y Datos (ml_ops, data_pipeline, nlp_analytics, predictive_maintenance, ai_consulting)
    AiData,
    /// Tecnología Financiera (neo_banking, defi_analytics, payment_gateway, insurance_tech, regtech)
    FinTech,
    /// Tecnología de la Salud (telemedicine, mental_health, clinical_trials, health_wearable, pharma_trace)
    HealthTech,
    /// Tecnología Verde (carbon_credits, smart_grid, ev_fleet, waste_management, green_bond)
    GreenTech,
    /// Tecnología Educativa (adaptive_learning, skill_assessment, virtual_classroom, ed_corporate, ed_neurodiverse)
    EdTech,
    /// Tecnología Inmobiliaria (smart_buildings, property_marketplace, str_analytics, cowork_manager, prop_token)
    PropTech,
    /// Tecnología Jurídica (contract_review, legal_research, compliance_monitor, ip_manager, dispute_resolution)
    LegalTech,
}

impl NicheCategory {
    /// All niche category variants.
    pub const ALL: [NicheCategory; 7] = [
        NicheCategory::AiData,
        NicheCategory::FinTech,
        NicheCategory::HealthTech,
        NicheCategory::GreenTech,
        NicheCategory::EdTech,
        NicheCategory::PropTech,
        NicheCategory::LegalTech,
    ];

    /// Number of categories.
    pub const COUNT: usize = 7;

    /// Returns the string identifier for this category.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::AiData => "ai_data",
            Self::FinTech => "fintech",
            Self::HealthTech => "healthtech",
            Self::GreenTech => "greentech",
            Self::EdTech => "edtech",
            Self::PropTech => "proptech",
            Self::LegalTech => "legaltech",
        }
    }

    /// Returns the human-readable display name (Spanish).
    pub fn display_name(&self) -> &'static str {
        match self {
            Self::AiData => "IA y Datos",
            Self::FinTech => "Tecnología Financiera",
            Self::HealthTech => "Tecnología de la Salud",
            Self::GreenTech => "Tecnología Verde",
            Self::EdTech => "Tecnología Educativa",
            Self::PropTech => "Tecnología Inmobiliaria",
            Self::LegalTech => "Tecnología Jurídica",
        }
    }

    /// Returns the compliance standards required for this category.
    pub fn compliance_standards(&self) -> &[crate::compliance::ComplianceStandard] {
        use crate::compliance::ComplianceStandard;
        match self {
            Self::AiData => &[ComplianceStandard::Gdpr, ComplianceStandard::Iso27001, ComplianceStandard::Soc2],
            Self::FinTech => &[ComplianceStandard::PciDss, ComplianceStandard::AmlKyc, ComplianceStandard::Sox, ComplianceStandard::Gdpr],
            Self::HealthTech => &[ComplianceStandard::Hipaa, ComplianceStandard::Gdpr, ComplianceStandard::Soc2],
            Self::GreenTech => &[ComplianceStandard::Iso27001, ComplianceStandard::Gdpr],
            Self::EdTech => &[ComplianceStandard::Coppa, ComplianceStandard::Gdpr, ComplianceStandard::Soc2],
            Self::PropTech => &[ComplianceStandard::Gdpr, ComplianceStandard::Sox, ComplianceStandard::Iso27001],
            Self::LegalTech => &[ComplianceStandard::Sox, ComplianceStandard::Soc2, ComplianceStandard::Gdpr, ComplianceStandard::Iso27001],
        }
    }

    /// Parse from string identifier.
    pub fn from_str_lossy(s: &str) -> Option<Self> {
        match s.to_lowercase().as_str() {
            "ai_data" | "ai-data" | "aidata" => Some(Self::AiData),
            "fintech" | "fin_tech" | "fin-tech" => Some(Self::FinTech),
            "healthtech" | "health_tech" | "health-tech" => Some(Self::HealthTech),
            "greentech" | "green_tech" | "green-tech" => Some(Self::GreenTech),
            "edtech" | "ed_tech" | "ed-tech" => Some(Self::EdTech),
            "proptech" | "prop_tech" | "prop-tech" => Some(Self::PropTech),
            "legaltech" | "legal_tech" | "legal-tech" => Some(Self::LegalTech),
            _ => None,
        }
    }
}

impl fmt::Display for NicheCategory {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_categories_count() {
        assert_eq!(NicheCategory::ALL.len(), NicheCategory::COUNT);
    }

    #[test]
    fn category_roundtrip() {
        for cat in NicheCategory::ALL {
            let s = cat.as_str();
            assert_eq!(NicheCategory::from_str_lossy(s), Some(cat));
        }
    }

    #[test]
    fn category_from_str_lossy() {
        assert_eq!(NicheCategory::from_str_lossy("AI_DATA"), Some(NicheCategory::AiData));
        assert_eq!(NicheCategory::from_str_lossy("FinTech"), Some(NicheCategory::FinTech));
        assert_eq!(NicheCategory::from_str_lossy("unknown"), None);
    }

    #[test]
    fn category_display_name() {
        assert_eq!(NicheCategory::HealthTech.display_name(), "Tecnología de la Salud");
    }

    #[test]
    fn category_compliance_standards() {
        let fintech = NicheCategory::FinTech.compliance_standards();
        assert!(fintech.len() >= 3);
    }
}
