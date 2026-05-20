//! Domain rule type definitions.

use regex::Regex;
use serde::{Deserialize, Serialize};
use std::fmt;

use crate::categories::NicheCategory;
use crate::verdict::{ActionCategory, SafetyVerdict};

// ---------------------------------------------------------------------------
// DomainRule
// ---------------------------------------------------------------------------

/// A single domain-specific safety rule.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DomainRule {
    /// Unique rule name (e.g., "fintech_unauthorized_transfer").
    pub name: String,
    /// The niche category this rule applies to.
    pub niche_category: NicheCategory,
    /// Human-readable description.
    pub description: String,
    /// The action category this rule targets.
    pub action_category: ActionCategory,
    /// Regex pattern to detect the condition.
    pub pattern: String,
    /// The verdict to apply when the pattern matches.
    pub verdict: SafetyVerdict,
    /// Human-readable message shown when triggered.
    pub message: String,
    /// Associated compliance standards (if any).
    pub compliance_standards: Vec<String>,

    #[serde(skip)]
    compiled: Option<Regex>,
}

impl DomainRule {
    /// Create a new domain rule.
    pub fn new(
        name: &str,
        niche_category: NicheCategory,
        description: &str,
        action_category: ActionCategory,
        pattern: &str,
        verdict: SafetyVerdict,
        message: &str,
        compliance_standards: Vec<&str>,
    ) -> Self {
        let compiled = Regex::new(pattern).ok();
        Self {
            name: name.to_string(),
            niche_category,
            description: description.to_string(),
            action_category,
            pattern: pattern.to_string(),
            verdict,
            message: message.to_string(),
            compliance_standards: compliance_standards.iter().map(|s| s.to_string()).collect(),
            compiled,
        }
    }

    /// Check if this rule matches the given action config.
    pub fn matches(&self, action_type: &str, config: &serde_json::Value) -> bool {
        if let Some(ref re) = self.compiled {
            let searchable = Self::to_searchable(action_type, config);
            re.is_match(&searchable)
        } else {
            false
        }
    }

    /// Convert action type + config to a searchable string.
    fn to_searchable(action_type: &str, config: &serde_json::Value) -> String {
        let mut parts = vec![action_type.to_string()];
        if let Some(obj) = config.as_object() {
            for (key, value) in obj {
                parts.push(format!("{}={}", key, value));
            }
        } else {
            parts.push(config.to_string());
        }
        parts.join(" ")
    }
}

impl fmt::Display for DomainRule {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "DomainRule({}:{})", self.niche_category, self.name)
    }
}
