//! Compliance type definitions — regulatory standards and result types.

use serde::{Deserialize, Serialize};
use std::fmt;

// ---------------------------------------------------------------------------
// ComplianceStandard
// ---------------------------------------------------------------------------

/// Regulatory compliance standards supported by the safety gate.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum ComplianceStandard {
    /// Health Insurance Portability and Accountability Act (US)
    Hipaa,
    /// Payment Card Industry Data Security Standard
    PciDss,
    /// General Data Protection Regulation (EU)
    Gdpr,
    /// Sarbanes-Oxley Act (US)
    Sox,
    /// Anti-Money Laundering / Know Your Customer
    AmlKyc,
    /// Children's Online Privacy Protection Act (US)
    Coppa,
    /// ISO/IEC 27001 Information Security Management
    Iso27001,
    /// SOC 2 Type II Service Organization Control
    Soc2,
}

impl ComplianceStandard {
    /// All standards.
    pub const ALL: [ComplianceStandard; 8] = [
        ComplianceStandard::Hipaa,
        ComplianceStandard::PciDss,
        ComplianceStandard::Gdpr,
        ComplianceStandard::Sox,
        ComplianceStandard::AmlKyc,
        ComplianceStandard::Coppa,
        ComplianceStandard::Iso27001,
        ComplianceStandard::Soc2,
    ];

    /// String identifier.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Hipaa => "hipaa",
            Self::PciDss => "pci_dss",
            Self::Gdpr => "gdpr",
            Self::Sox => "sox",
            Self::AmlKyc => "aml_kyc",
            Self::Coppa => "coppa",
            Self::Iso27001 => "iso_27001",
            Self::Soc2 => "soc2",
        }
    }

    /// Human-readable name.
    pub fn display_name(&self) -> &'static str {
        match self {
            Self::Hipaa => "HIPAA",
            Self::PciDss => "PCI-DSS",
            Self::Gdpr => "GDPR",
            Self::Sox => "SOX",
            Self::AmlKyc => "AML/KYC",
            Self::Coppa => "COPPA",
            Self::Iso27001 => "ISO 27001",
            Self::Soc2 => "SOC 2",
        }
    }

    /// Parse from string.
    pub fn from_str_lossy(s: &str) -> Option<Self> {
        match s.to_lowercase().replace("-", "_").replace(" ", "").as_str() {
            "hipaa" => Some(Self::Hipaa),
            "pci_dss" | "pcidss" | "pci" => Some(Self::PciDss),
            "gdpr" => Some(Self::Gdpr),
            "sox" => Some(Self::Sox),
            "aml_kyc" | "amlkyc" | "aml" | "kyc" => Some(Self::AmlKyc),
            "coppa" => Some(Self::Coppa),
            "iso_27001" | "iso27001" | "iso2701" => Some(Self::Iso27001),
            "soc2" | "soc_2" | "soc" => Some(Self::Soc2),
            _ => None,
        }
    }
}

impl fmt::Display for ComplianceStandard {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.as_str())
    }
}

// ---------------------------------------------------------------------------
// ComplianceResult
// ---------------------------------------------------------------------------

/// Result of a compliance check against a regulatory standard.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComplianceResult {
    /// The standard that was checked.
    pub standard: ComplianceStandard,
    /// Whether the action is compliant with this standard.
    pub compliant: bool,
    /// List of violations found.
    pub violations: Vec<String>,
    /// List of recommendations to achieve compliance.
    pub recommendations: Vec<String>,
    /// Risk level: "low", "medium", "high", "critical".
    pub risk_level: String,
}

impl ComplianceResult {
    /// Create a compliant result with no violations.
    pub fn compliant(standard: ComplianceStandard) -> Self {
        Self {
            standard,
            compliant: true,
            violations: Vec::new(),
            recommendations: Vec::new(),
            risk_level: "low".to_string(),
        }
    }

    /// Create a non-compliant result.
    pub fn non_compliant(
        standard: ComplianceStandard,
        violations: Vec<String>,
        recommendations: Vec<String>,
        risk_level: &str,
    ) -> Self {
        Self {
            standard,
            compliant: false,
            violations,
            recommendations,
            risk_level: risk_level.to_string(),
        }
    }
}

impl fmt::Display for ComplianceResult {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "ComplianceResult({}: {})",
            self.standard.display_name(),
            if self.compliant { "COMPLIANT" } else { "VIOLATION" }
        )
    }
}
