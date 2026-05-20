//! Domain rule definitions: HealthTech, GreenTech categories.

use crate::categories::NicheCategory;
use crate::verdict::{ActionCategory, SafetyVerdict};

use crate::domain_rules::rule_types::DomainRule;
use super::DomainRuleSet;

impl DomainRuleSet {
    /// Reglas de Tecnología de la Salud (5).
    pub(super) fn healthtech_rules() -> Vec<DomainRule> {
        vec![
            DomainRule::new(
                "healthtech_phi_access",
                NicheCategory::HealthTech,
                "Access to Protected Health Information",
                ActionCategory::Moderate,
                r"(?:phi|health_record|medical_record|patient_data|clinical_data)",
                SafetyVerdict::Approve,
                "PHI access requires approval — HIPAA compliance required",
                vec!["hipaa"],
            ),
            DomainRule::new(
                "healthtech_prescription_mod",
                NicheCategory::HealthTech,
                "Prescription modification without authorization",
                ActionCategory::Destructive,
                r"(?:prescription|medication).*(?:modify|change|update|alter)",
                SafetyVerdict::Deny,
                "Unauthorized prescription modification — DENIED per patient safety",
                vec!["hipaa"],
            ),
            DomainRule::new(
                "healthtech_diagnosis_override",
                NicheCategory::HealthTech,
                "Manual diagnosis override in clinical system",
                ActionCategory::Moderate,
                r"(?:diagnosis_override|override_diagnosis|clinical_override|force_diagnosis)",
                SafetyVerdict::Approve,
                "Diagnosis override requires medical professional approval",
                vec!["hipaa", "soc2"],
            ),
            DomainRule::new(
                "healthtech_patient_export",
                NicheCategory::HealthTech,
                "Patient data export",
                ActionCategory::Destructive,
                r"(?:patient_export|export_patient|download_records|medical_data_export)",
                SafetyVerdict::Confirm,
                "Patient data export requires confirmation — verify HIPAA compliance",
                vec!["hipaa", "gdpr"],
            ),
            DomainRule::new(
                "healthtech_device_config",
                NicheCategory::HealthTech,
                "Medical device configuration change",
                ActionCategory::System,
                r"(?:device_config|wearable_config|monitor_setup|device_calibration)",
                SafetyVerdict::Confirm,
                "Medical device configuration change requires confirmation",
                vec!["hipaa"],
            ),
        ]
    }

    /// Reglas de Tecnología Verde (5).
    pub(super) fn greentech_rules() -> Vec<DomainRule> {
        vec![
            DomainRule::new(
                "greentech_carbon_adjust",
                NicheCategory::GreenTech,
                "Carbon credit adjustment",
                ActionCategory::Financial,
                r"(?:carbon_credit|credit_adjust|offset_modify|emission_offset)",
                SafetyVerdict::Approve,
                "Carbon credit adjustment requires approval — audit trail required",
                vec!["iso_27001"],
            ),
            DomainRule::new(
                "greentech_grid_reconfig",
                NicheCategory::GreenTech,
                "Smart grid reconfiguration",
                ActionCategory::System,
                r"(?:grid_reconfig|smart_grid_change|load_balance_modify|grid_topology)",
                SafetyVerdict::Confirm,
                "Grid reconfiguration requires confirmation — infrastructure stability at risk",
                vec!["iso_27001"],
            ),
            DomainRule::new(
                "greentech_sensor_override",
                NicheCategory::GreenTech,
                "Environmental sensor override",
                ActionCategory::Moderate,
                r"(?:sensor_override|override_sensor|bypass_monitor|ignore_reading)",
                SafetyVerdict::Confirm,
                "Sensor override requires confirmation — data integrity at risk",
                vec!["iso_27001"],
            ),
            DomainRule::new(
                "greentech_waste_reclassify",
                NicheCategory::GreenTech,
                "Waste classification change",
                ActionCategory::Moderate,
                r"(?:waste_reclassify|reclassify_waste|waste_category_change|hazardous_reclass)",
                SafetyVerdict::Approve,
                "Waste reclassification requires approval — regulatory compliance",
                vec!["iso_27001", "gdpr"],
            ),
            DomainRule::new(
                "greentech_fleet_decommission",
                NicheCategory::GreenTech,
                "EV fleet decommission",
                ActionCategory::Destructive,
                r"(?:fleet_decommission|decommission_ev|retire_vehicle|fleet_remove)",
                SafetyVerdict::Confirm,
                "Fleet decommission requires confirmation — verify asset tracking",
                vec!["iso_27001"],
            ),
        ]
    }
}
