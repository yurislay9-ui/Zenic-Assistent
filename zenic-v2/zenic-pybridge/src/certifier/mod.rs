//! Blueprint Certification Engine for Zenic-Agents (Phase 6.D).
//!
//! Converts completed YAML templates into CertifiedBlueprints with
//! ECDSA signing, integrity verification, and integration with the
//! existing Phase 5 Blueprint system.
//!
//! # Architecture
//!
//! The certification pipeline:
//!
//! 1. Completed template dict (from completer_finalize) → input
//! 2. Template validation (all required fields filled)
//! 3. BlueprintConfig construction from template data
//! 4. ECDSA signature generation over canonical serialized form
//! 5. CertifiedBlueprint with signature, hash, and metadata
//! 6. Export as YAML dict or string for Phase 5 Blueprint loader
//!
//! # CertifiedBlueprint Structure
//!
//! A CertifiedBlueprint contains:
//! - **config**: BlueprintConfig with all business-specific settings
//! - **metadata**: Certification metadata (timestamp, version, niche info)
//! - **integrity**: SHA-256 hash of canonical form + ECDSA signature
//! - **compliance**: Compliance standards extracted from niche definition
//! - **audit_trail**: Hash chain linking template → certified blueprint
//!
//! # Design Decisions
//!
//! - No `unwrap` or `panic` — all errors handled explicitly
//! - All external input validated before processing
//! - ECDSA signing uses the existing license module's primitives
//! - Hash chain provides tamper-proof audit trail
//! - Certification is idempotent: same template → same hash
//! - Blueprint version follows semantic versioning (major.minor.patch)
//!
//! # PyO3 Exposed Types
//!
//! - `BlueprintConfig` — structured blueprint configuration
//! - `CertifiedBlueprint` — signed, validated blueprint
//! - `CertificationResult` — result of the certification process
//! - `CertificationStatus` — status enum for certification states
//!
//! # PyO3 Exposed Functions
//!
//! - `certifier_from_template(template_dict)` — create BlueprintConfig from template
//! - `certifier_sign(config, private_key)` — sign a BlueprintConfig
//! - `certifier_verify(blueprint, public_key)` — verify a CertifiedBlueprint
//! - `certifier_to_blueprint_dict(blueprint)` — export to dict for Phase 5
//! - `certifier_compute_hash(config)` — compute canonical hash
//! - `certifier_validate_config(config)` — validate BlueprintConfig completeness
//! - `certifier_export_yaml(blueprint)` — export certified blueprint as YAML string

mod api_export;
mod api_from_template;
mod api_sign_verify;
mod blueprint;
mod config;
mod helpers;
mod result;
mod schema_types;
mod types;

pub use api_export::*;
pub use api_from_template::*;
pub use api_sign_verify::*;
pub use blueprint::*;
pub use config::*;
pub use result::*;
pub use schema_types::*;
pub use types::*;

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_certification_status_as_str() {
        assert_eq!(CertificationStatus::Draft.as_str(), "draft");
        assert_eq!(CertificationStatus::Signed.as_str(), "signed");
        assert_eq!(CertificationStatus::Verified.as_str(), "verified");
        assert_eq!(CertificationStatus::Revoked.as_str(), "revoked");
        assert_eq!(CertificationStatus::Error.as_str(), "error");
    }

    #[test]
    fn test_blueprint_config_creation() {
        let config = BlueprintConfig::new(
            "telemedicine".to_string(),
            "Test Clinic".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "critical".to_string(),
        );
        assert_eq!(config.niche_id(), "telemedicine");
        assert_eq!(config.business_name(), "Test Clinic");
        assert!(config.is_certifiable());
    }

    #[test]
    fn test_blueprint_config_certifiable_validation() {
        let valid = BlueprintConfig::new(
            "test".to_string(),
            "Business".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "high".to_string(),
        );
        assert!(valid.is_certifiable());

        let empty_name = BlueprintConfig::new(
            "test".to_string(),
            "".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "high".to_string(),
        );
        assert!(!empty_name.is_certifiable());
    }

    #[test]
    fn test_blueprint_config_add_compliance() {
        let mut config = BlueprintConfig::new(
            "test".to_string(),
            "Business".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "high".to_string(),
        );
        config.add_compliance("HIPAA".to_string()).unwrap();
        config.add_compliance("GDPR".to_string()).unwrap();
        config.add_compliance("HIPAA".to_string()).unwrap(); // duplicate ignored
        assert_eq!(config.compliance.len(), 2);
    }

    #[test]
    fn test_blueprint_config_settings() {
        let mut config = BlueprintConfig::new(
            "test".to_string(),
            "Business".to_string(),
            "llc".to_string(),
            "fintech".to_string(),
            "critical".to_string(),
        );
        config.set_setting("api_key_ref".to_string(), "vault://api/key".to_string());
        config.set_setting("base_currency".to_string(), "USD".to_string());
        assert_eq!(config.settings.len(), 2);
    }

    #[test]
    fn test_compute_canonical_hash_deterministic() {
        let config1 = BlueprintConfig::new(
            "telemedicine".to_string(),
            "Clinic A".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "critical".to_string(),
        );
        let config2 = BlueprintConfig::new(
            "telemedicine".to_string(),
            "Clinic A".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "critical".to_string(),
        );
        let hash1 = helpers::compute_canonical_hash(&config1);
        let hash2 = helpers::compute_canonical_hash(&config2);
        assert_eq!(hash1, hash2, "Same config must produce same hash");
    }

    #[test]
    fn test_compute_canonical_hash_different_configs() {
        let config1 = BlueprintConfig::new(
            "telemedicine".to_string(),
            "Clinic A".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "critical".to_string(),
        );
        let config2 = BlueprintConfig::new(
            "telemedicine".to_string(),
            "Clinic B".to_string(),
            "llc".to_string(),
            "health".to_string(),
            "critical".to_string(),
        );
        let hash1 = helpers::compute_canonical_hash(&config1);
        let hash2 = helpers::compute_canonical_hash(&config2);
        assert_ne!(hash1, hash2, "Different configs must produce different hashes");
    }

    #[test]
    fn test_db_table_def_creation() {
        let mut table = DbTableDef::new("users".to_string(), "id".to_string());
        table.add_column(ColumnDef::py_new("id".to_string(), "uuid".to_string()));
        table.add_column(ColumnDef::py_new("email".to_string(), "text".to_string()));
        table.set_encrypted(true);
        assert_eq!(table.table_name, "users");
        assert_eq!(table.columns.len(), 2);
        assert!(table.encrypted);
    }

    #[test]
    fn test_monitor_def_creation() {
        let mut monitor = MonitorDef::new(
            "health_check".to_string(),
            "liviano".to_string(),
            "Health Check".to_string(),
        );
        monitor.set_interval(60);
        monitor.set_threshold(0.5);
        assert_eq!(monitor.monitor_id, "health_check");
        assert_eq!(monitor.interval_seconds, 60);
    }

    #[test]
    fn test_action_def_creation() {
        let mut action = ActionDef::new(
            "delete_record".to_string(),
            "db".to_string(),
            "Delete Record".to_string(),
        );
        action.set_requires_approval(true);
        action.set_risk_level("critical".to_string());
        assert!(action.requires_approval);
        assert_eq!(action.risk_level, "critical");
    }

    #[test]
    fn test_action_def_risk_level_validation() {
        let mut action = ActionDef::new(
            "test".to_string(),
            "db".to_string(),
            "Test".to_string(),
        );
        action.set_risk_level("high".to_string());
        assert_eq!(action.risk_level, "high");

        // Invalid level should be ignored
        action.set_risk_level("invalid".to_string());
        assert_eq!(action.risk_level, "high"); // Unchanged
    }

    #[test]
    fn test_column_def_creation() {
        let mut col = ColumnDef::py_new("email".to_string(), "text".to_string());
        col.set_unique(true);
        col.set_indexed(true);
        col.set_nullable(false);
        assert_eq!(col.name, "email");
        assert!(col.unique);
        assert!(col.indexed);
        assert!(!col.nullable);
    }

    #[test]
    fn test_build_default_monitors_low() {
        let monitors = api_from_template::build_default_monitors("low");
        assert!(monitors.len() >= 1);
        assert!(monitors.iter().any(|m| m.monitor_id == "health_check"));
    }

    #[test]
    fn test_build_default_monitors_critical() {
        let monitors = api_from_template::build_default_monitors("critical");
        assert!(monitors.len() >= 3);
        assert!(monitors.iter().any(|m| m.monitor_id == "intrusion_detection"));
        assert!(monitors.iter().any(|m| m.monitor_id == "data_integrity"));
    }

    #[test]
    fn test_build_default_db_schema() {
        let tables = api_from_template::build_default_db_schema("telemedicine");
        assert!(tables.len() >= 2); // users + audit_log at minimum
        assert!(tables.iter().any(|t| t.table_name == "users"));
        assert!(tables.iter().any(|t| t.table_name == "audit_log"));
    }

    #[test]
    fn test_generate_blueprint_id_format() {
        let id = helpers::generate_blueprint_id("telemedicine");
        assert!(id.starts_with("bp-telemedicine-"));
    }

    #[test]
    fn test_certification_result_default() {
        let result = CertificationResult {
            success: false,
            blueprint: None,
            config: None,
            status: CertificationStatus::Error,
            content_hash: String::new(),
            elapsed_ms: 0,
            warnings: Vec::new(),
            errors: vec!["test error".to_string()],
        };
        assert!(!result.success);
        assert_eq!(result.errors.len(), 1);
    }
}
