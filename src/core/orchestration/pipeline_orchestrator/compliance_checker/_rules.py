"""
Compliance Checker — Built-in rule definitions for all standards.
"""

from __future__ import annotations

from typing import List

from ._types import ComplianceRule, ComplianceSeverity, ComplianceStandard


def build_hipaa_rules() -> List[ComplianceRule]:
    """Build HIPAA compliance rules."""
    std = ComplianceStandard.HIPAA
    return [
        ComplianceRule(
            rule_id="hipaa.encryption_at_rest",
            standard=std,
            description="PHI must be encrypted at rest",
            severity=ComplianceSeverity.CRITICAL,
            check_fn=lambda ctx: ctx.get("encryption_at_rest", False),
            remediation="Enable encryption for all data stores containing PHI.",
        ),
        ComplianceRule(
            rule_id="hipaa.encryption_in_transit",
            standard=std,
            description="PHI must be encrypted in transit",
            severity=ComplianceSeverity.CRITICAL,
            check_fn=lambda ctx: ctx.get("encryption_in_transit", False),
            remediation="Enable TLS for all data transmission channels.",
        ),
        ComplianceRule(
            rule_id="hipaa.access_controls",
            standard=std,
            description="Access controls must be implemented for PHI",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("access_controls", False),
            remediation="Implement role-based access controls.",
        ),
        ComplianceRule(
            rule_id="hipaa.audit_logging",
            standard=std,
            description="Audit logging must be enabled for PHI access",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("audit_logging", False),
            remediation="Enable comprehensive audit logging.",
        ),
        ComplianceRule(
            rule_id="hipaa.minimum_necessary",
            standard=std,
            description="Only minimum necessary PHI should be accessed",
            severity=ComplianceSeverity.MEDIUM,
            check_fn=lambda ctx: ctx.get("minimum_necessary", True),
            remediation="Implement data minimization controls.",
        ),
    ]


def build_pci_dss_rules() -> List[ComplianceRule]:
    """Build PCI-DSS compliance rules."""
    std = ComplianceStandard.PCI_DSS
    return [
        ComplianceRule(
            rule_id="pci_dss.card_data_encryption",
            standard=std,
            description="Cardholder data must be encrypted",
            severity=ComplianceSeverity.CRITICAL,
            check_fn=lambda ctx: ctx.get("card_data_encrypted", False),
            remediation="Encrypt all cardholder data at rest and in transit.",
        ),
        ComplianceRule(
            rule_id="pci_dss.network_segmentation",
            standard=std,
            description="Cardholder data environment must be segmented",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("network_segmentation", False),
            remediation="Implement network segmentation for CDE.",
        ),
        ComplianceRule(
            rule_id="pci_dss.vulnerability_scanning",
            standard=std,
            description="Regular vulnerability scans must be performed",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("vulnerability_scanning", False),
            remediation="Schedule regular vulnerability scans.",
        ),
        ComplianceRule(
            rule_id="pci_dss.strong_authentication",
            standard=std,
            description="Strong authentication must be used for CDE access",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("strong_authentication", False),
            remediation="Implement MFA for all CDE access.",
        ),
    ]


def build_soc2_rules() -> List[ComplianceRule]:
    """Build SOC 2 compliance rules."""
    std = ComplianceStandard.SOC2
    return [
        ComplianceRule(
            rule_id="soc2.logical_access",
            standard=std,
            description="Logical access controls must be in place",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("logical_access_controls", False),
            remediation="Implement logical access controls.",
        ),
        ComplianceRule(
            rule_id="soc2.change_management",
            standard=std,
            description="Change management procedures must be followed",
            severity=ComplianceSeverity.MEDIUM,
            check_fn=lambda ctx: ctx.get("change_management", True),
            remediation="Implement formal change management procedures.",
        ),
        ComplianceRule(
            rule_id="soc2.incident_response",
            standard=std,
            description="Incident response plan must be in place",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("incident_response_plan", False),
            remediation="Develop and test an incident response plan.",
        ),
    ]


def build_gdpr_rules() -> List[ComplianceRule]:
    """Build GDPR compliance rules."""
    std = ComplianceStandard.GDPR
    return [
        ComplianceRule(
            rule_id="gdpr.consent_management",
            standard=std,
            description="Consent must be obtained for personal data processing",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("consent_management", False),
            remediation="Implement consent management system.",
        ),
        ComplianceRule(
            rule_id="gdpr.right_to_erasure",
            standard=std,
            description="Right to erasure must be supported",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("right_to_erasure", False),
            remediation="Implement data deletion capabilities.",
        ),
        ComplianceRule(
            rule_id="gdpr.data_minimization",
            standard=std,
            description="Only necessary personal data should be collected",
            severity=ComplianceSeverity.MEDIUM,
            check_fn=lambda ctx: ctx.get("data_minimization", True),
            remediation="Implement data minimization practices.",
        ),
        ComplianceRule(
            rule_id="gdpr.breach_notification",
            standard=std,
            description="Data breach notification procedures must be in place",
            severity=ComplianceSeverity.CRITICAL,
            check_fn=lambda ctx: ctx.get("breach_notification", False),
            remediation="Implement 72-hour breach notification procedures.",
        ),
    ]


def build_sox_rules() -> List[ComplianceRule]:
    """Build SOX compliance rules."""
    std = ComplianceStandard.SOX
    return [
        ComplianceRule(
            rule_id="sox.internal_controls",
            standard=std,
            description="Internal controls over financial reporting must exist",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("internal_controls", False),
            remediation="Implement internal controls for financial reporting.",
        ),
        ComplianceRule(
            rule_id="sox.segregation_of_duties",
            standard=std,
            description="Segregation of duties must be enforced",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("segregation_of_duties", False),
            remediation="Implement role-based segregation of duties.",
        ),
        ComplianceRule(
            rule_id="sox.audit_trail",
            standard=std,
            description="Complete audit trail for financial data must exist",
            severity=ComplianceSeverity.CRITICAL,
            check_fn=lambda ctx: ctx.get("financial_audit_trail", False),
            remediation="Implement tamper-proof audit trail for financial data.",
        ),
    ]


def build_iso27001_rules() -> List[ComplianceRule]:
    """Build ISO 27001 compliance rules."""
    std = ComplianceStandard.ISO_27001
    return [
        ComplianceRule(
            rule_id="iso27001.risk_assessment",
            standard=std,
            description="Information security risk assessment must be performed",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("risk_assessment", False),
            remediation="Conduct regular information security risk assessments.",
        ),
        ComplianceRule(
            rule_id="iso27001.security_policy",
            standard=std,
            description="Information security policy must be defined",
            severity=ComplianceSeverity.MEDIUM,
            check_fn=lambda ctx: ctx.get("security_policy", False),
            remediation="Define and maintain information security policy.",
        ),
    ]


def build_nist_rules() -> List[ComplianceRule]:
    """Build NIST compliance rules."""
    std = ComplianceStandard.NIST
    return [
        ComplianceRule(
            rule_id="nist.identify",
            standard=std,
            description="Asset management and risk assessment must be in place",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("asset_management", False),
            remediation="Implement asset management and risk identification.",
        ),
        ComplianceRule(
            rule_id="nist.protect",
            standard=std,
            description="Access controls and data security must be implemented",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("access_controls", False),
            remediation="Implement access controls and data protection.",
        ),
        ComplianceRule(
            rule_id="nist.detect",
            standard=std,
            description="Security event detection must be in place",
            severity=ComplianceSeverity.MEDIUM,
            check_fn=lambda ctx: ctx.get("anomaly_detection", False),
            remediation="Implement security monitoring and anomaly detection.",
        ),
        ComplianceRule(
            rule_id="nist.respond",
            standard=std,
            description="Incident response procedures must be defined",
            severity=ComplianceSeverity.HIGH,
            check_fn=lambda ctx: ctx.get("incident_response", False),
            remediation="Define and test incident response procedures.",
        ),
        ComplianceRule(
            rule_id="nist.recover",
            standard=std,
            description="Recovery planning must be in place",
            severity=ComplianceSeverity.MEDIUM,
            check_fn=lambda ctx: ctx.get("recovery_planning", False),
            remediation="Implement recovery planning and procedures.",
        ),
    ]


def build_all_default_rules() -> List[ComplianceRule]:
    """Build all built-in compliance rules."""
    rules: List[ComplianceRule] = []
    rules.extend(build_hipaa_rules())
    rules.extend(build_pci_dss_rules())
    rules.extend(build_soc2_rules())
    rules.extend(build_gdpr_rules())
    rules.extend(build_sox_rules())
    rules.extend(build_iso27001_rules())
    rules.extend(build_nist_rules())
    return rules
