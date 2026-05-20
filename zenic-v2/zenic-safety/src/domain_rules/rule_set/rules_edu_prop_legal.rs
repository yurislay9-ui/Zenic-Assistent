//! Domain rule definitions: EdTech, PropTech, LegalTech categories.

use crate::categories::NicheCategory;
use crate::verdict::{ActionCategory, SafetyVerdict};

use crate::domain_rules::rule_types::DomainRule;
use super::DomainRuleSet;

impl DomainRuleSet {
    /// Reglas de Tecnología Educativa (5).
    pub(super) fn edtech_rules() -> Vec<DomainRule> {
        vec![
            DomainRule::new(
                "edtech_minor_data",
                NicheCategory::EdTech,
                "Access to minor/student data",
                ActionCategory::Moderate,
                r"(?:minor_data|student_data|child_data|underage|under_18)",
                SafetyVerdict::Approve,
                "Minor data access requires approval — COPPA compliance required",
                vec!["coppa"],
            ),
            DomainRule::new(
                "edtech_grade_modify",
                NicheCategory::EdTech,
                "Grade or assessment modification",
                ActionCategory::Destructive,
                r"(?:grade_modify|change_grade|assessment_override|score_change)",
                SafetyVerdict::Deny,
                "Unauthorized grade modification — DENIED per academic integrity",
                vec!["coppa", "soc2"],
            ),
            DomainRule::new(
                "edtech_content_filter",
                NicheCategory::EdTech,
                "Content filter bypass attempt",
                ActionCategory::System,
                r"(?:filter_bypass|bypass_filter|content_unblock|unblock_site)",
                SafetyVerdict::Deny,
                "Content filter bypass — DENIED — student safety protection",
                vec!["coppa"],
            ),
            DomainRule::new(
                "edtech_bulk_export",
                NicheCategory::EdTech,
                "Bulk student data export",
                ActionCategory::Destructive,
                r"(?:bulk_student_export|export_roster|download_grades|class_export)",
                SafetyVerdict::Confirm,
                "Bulk student data export requires confirmation — verify COPPA/GDPR compliance",
                vec!["coppa", "gdpr"],
            ),
            DomainRule::new(
                "edtech_curriculum_change",
                NicheCategory::EdTech,
                "Curriculum or course structure change",
                ActionCategory::System,
                r"(?:curriculum_change|course_modify|syllabus_update|learning_path_change)",
                SafetyVerdict::Confirm,
                "Curriculum change requires confirmation — impact on enrolled students",
                vec!["soc2"],
            ),
        ]
    }

    /// Reglas de Tecnología Inmobiliaria (5).
    pub(super) fn proptech_rules() -> Vec<DomainRule> {
        vec![
            DomainRule::new(
                "proptech_transaction",
                NicheCategory::PropTech,
                "Property transaction without verification",
                ActionCategory::Financial,
                r"(?:property_transaction|real_estate_deal|buy_property|sell_property)",
                SafetyVerdict::Approve,
                "Property transaction requires approval — verify legal compliance",
                vec!["sox", "gdpr"],
            ),
            DomainRule::new(
                "proptech_lease_terminate",
                NicheCategory::PropTech,
                "Lease early termination",
                ActionCategory::Destructive,
                r"(?:lease_terminate|terminate_lease|cancel_lease|early_termination)",
                SafetyVerdict::Confirm,
                "Lease termination requires confirmation — verify contractual obligations",
                vec!["sox"],
            ),
            DomainRule::new(
                "proptech_valuation_change",
                NicheCategory::PropTech,
                "Property valuation modification",
                ActionCategory::Financial,
                r"(?:valuation_change|appraisal_modify|value_adjust|price_revalue)",
                SafetyVerdict::Approve,
                "Valuation change requires approval — SOX compliance for financial reporting",
                vec!["sox", "iso_27001"],
            ),
            DomainRule::new(
                "proptech_tenant_data",
                NicheCategory::PropTech,
                "Tenant personal data access",
                ActionCategory::Moderate,
                r"(?:tenant_data|tenant_info|renter_data|occupant_info)",
                SafetyVerdict::Confirm,
                "Tenant data access requires confirmation — GDPR privacy compliance",
                vec!["gdpr"],
            ),
            DomainRule::new(
                "proptech_access_control",
                NicheCategory::PropTech,
                "Building access control modification",
                ActionCategory::System,
                r"(?:access_control|door_config|security_system|building_access)",
                SafetyVerdict::Confirm,
                "Access control modification requires confirmation — physical security",
                vec!["iso_27001"],
            ),
        ]
    }

    /// Reglas de Tecnología Jurídica (5).
    pub(super) fn legaltech_rules() -> Vec<DomainRule> {
        vec![
            DomainRule::new(
                "legaltech_contract_exec",
                NicheCategory::LegalTech,
                "Contract execution without review",
                ActionCategory::Financial,
                r"(?:contract_execute|execute_contract|sign_contract|contract_sign)",
                SafetyVerdict::Approve,
                "Contract execution requires approval — legal review mandatory",
                vec!["sox", "soc2"],
            ),
            DomainRule::new(
                "legaltech_document_delete",
                NicheCategory::LegalTech,
                "Legal document deletion",
                ActionCategory::Destructive,
                r"(?:document_delete|delete_legal|destroy_record|purge_document)",
                SafetyVerdict::Deny,
                "Legal document deletion — DENIED — document retention policy",
                vec!["sox", "soc2"],
            ),
            DomainRule::new(
                "legaltech_privilege",
                NicheCategory::LegalTech,
                "Attorney-client privilege data access",
                ActionCategory::Moderate,
                r"(?:privilege|attorney_client|legal_privilege|work_product)",
                SafetyVerdict::Approve,
                "Privileged data access requires approval — attorney-client privilege protection",
                vec!["soc2", "iso_27001"],
            ),
            DomainRule::new(
                "legaltech_compliance_config",
                NicheCategory::LegalTech,
                "Compliance monitoring configuration change",
                ActionCategory::System,
                r"(?:compliance_config|monitor_change|alert_threshold|compliance_rule_modify)",
                SafetyVerdict::Confirm,
                "Compliance config change requires confirmation — regulatory coverage at risk",
                vec!["sox", "iso_27001"],
            ),
            DomainRule::new(
                "legaltech_ip_transfer",
                NicheCategory::LegalTech,
                "Intellectual property transfer",
                ActionCategory::Financial,
                r"(?:ip_transfer|patent_transfer|trademark_assign|copyright_transfer)",
                SafetyVerdict::Approve,
                "IP transfer requires approval — legal verification mandatory",
                vec!["sox", "soc2", "gdpr"],
            ),
        ]
    }
}
