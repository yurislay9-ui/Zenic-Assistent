//! Business domain types for the global business assistance platform.
//!
//! [`BusinessDomain`] enumerates the popular niches that the system supports.
//! Each domain maps to one or more supernodes in the fractal DAG.
//! [`DomainCapability`] describes what a domain can do at a high level.

use serde::{Deserialize, Serialize};
use std::fmt;

// ---------------------------------------------------------------------------
// BusinessDomain
// ---------------------------------------------------------------------------

/// Popular global business niches supported by Zenic-Agents.
///
/// Each variant corresponds to a top-level domain in the fractal DAG.
/// The catalogue of supernodes is derived from these domains.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum BusinessDomain {
    // -- Commerce --
    ECommerce,
    Retail,

    // -- Food & Beverage --
    FoodService,

    // -- Health --
    Healthcare,
    Wellness,

    // -- Property --
    RealEstate,

    // -- Professional Services --
    Legal,
    Consulting,
    Accounting,

    // -- Logistics & Transportation --
    SupplyChain,
    Transportation,

    // -- Marketing --
    DigitalMarketing,

    // -- Education --
    Education,

    // -- Construction --
    Construction,

    // -- Tourism & Hospitality --
    Hospitality,

    // -- Manufacturing --
    Manufacturing,

    // -- Agriculture --
    Agriculture,

    // -- Technology --
    Saas,

    // -- Finance --
    Finance,

    // -- Human Resources --
    HumanResources,

    // -- Insurance --
    Insurance,

    // -- Energy --
    Energy,

    // -- Media & Entertainment --
    Media,

    // -- General / Cross-domain --
    GeneralBusiness,
}

impl BusinessDomain {
    /// Returns the canonical snake_case key used in catalog lookups and
    /// serialization.
    pub fn key(&self) -> &'static str {
        match self {
            Self::ECommerce => "ecommerce",
            Self::Retail => "retail",
            Self::FoodService => "food_service",
            Self::Healthcare => "healthcare",
            Self::Wellness => "wellness",
            Self::RealEstate => "real_estate",
            Self::Legal => "legal",
            Self::Consulting => "consulting",
            Self::Accounting => "accounting",
            Self::SupplyChain => "supply_chain",
            Self::Transportation => "transportation",
            Self::DigitalMarketing => "digital_marketing",
            Self::Education => "education",
            Self::Construction => "construction",
            Self::Hospitality => "hospitality",
            Self::Manufacturing => "manufacturing",
            Self::Agriculture => "agriculture",
            Self::Saas => "saas",
            Self::Finance => "finance",
            Self::HumanResources => "human_resources",
            Self::Insurance => "insurance",
            Self::Energy => "energy",
            Self::Media => "media",
            Self::GeneralBusiness => "general_business",
        }
    }

    /// Returns all defined domains.
    pub fn all() -> &'static [BusinessDomain] {
        &[
            Self::ECommerce,
            Self::Retail,
            Self::FoodService,
            Self::Healthcare,
            Self::Wellness,
            Self::RealEstate,
            Self::Legal,
            Self::Consulting,
            Self::Accounting,
            Self::SupplyChain,
            Self::Transportation,
            Self::DigitalMarketing,
            Self::Education,
            Self::Construction,
            Self::Hospitality,
            Self::Manufacturing,
            Self::Agriculture,
            Self::Saas,
            Self::Finance,
            Self::HumanResources,
            Self::Insurance,
            Self::Energy,
            Self::Media,
            Self::GeneralBusiness,
        ]
    }
}

impl fmt::Display for BusinessDomain {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.key())
    }
}

// ---------------------------------------------------------------------------
// DomainCapability
// ---------------------------------------------------------------------------

/// High-level capability descriptor for a business domain.
///
/// This is metadata that helps the runtime decide which subgraphs to load
/// and which routes to activate for a given business profile.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DomainCapability {
    /// The domain this capability belongs to.
    pub domain: BusinessDomain,
    /// Human-readable name.
    pub name: String,
    /// Short description of what this capability provides.
    pub description: String,
    /// Whether this capability requires external API access.
    pub requires_external_api: bool,
    /// Estimated memory footprint in bytes when the subgraph is loaded.
    pub memory_estimate_bytes: u64,
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn all_domains_are_unique() {
        let all = BusinessDomain::all();
        let mut seen = std::collections::HashSet::new();
        for d in all {
            assert!(seen.insert(d.key()), "duplicate domain key: {}", d.key());
        }
    }

    #[test]
    fn domain_key_matches_display() {
        for d in BusinessDomain::all() {
            assert_eq!(d.to_string(), d.key());
        }
    }

    #[test]
    fn domain_capability_serialization_roundtrip() {
        let cap = DomainCapability {
            domain: BusinessDomain::ECommerce,
            name: "Inventory Management".to_string(),
            description: "Track stock levels and reorder points".to_string(),
            requires_external_api: false,
            memory_estimate_bytes: 2048,
        };
        let json = serde_json::to_string(&cap).expect("serialize");
        let back: DomainCapability = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(cap, back);
    }

    #[test]
    fn domain_count() {
        assert_eq!(BusinessDomain::all().len(), 24);
    }
}
