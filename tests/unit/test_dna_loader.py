"""
Unit tests for DNALoader

Tests loading of YAML templates (logic_modules, domain_rules,
validation_gates, glossary), parsing of dataclasses, and
validation gate checking logic.
"""

import pytest

from src.core.dna_loader import (
    DNALoader, YAML_AVAILABLE,
)


# ============================================================
#  Sample YAML Data
# ============================================================

SAMPLE_LOGIC_MODULES = """
modules:
  - id: auth_jwt_standard
    domain: authentication
    description: Standard JWT authentication module
    code_block: "def create_jwt(): pass"
    dependencies: ["pyjwt"]
    verification_rule: "jwt_present"
    inputs: ["username", "password"]
    outputs: ["token"]
  - id: stripe_charge
    domain: payments
    description: Stripe payment charge
    code_block: "def charge(): pass"
    dependencies: ["stripe"]
    inputs: ["amount", "currency"]
    outputs: ["charge_id"]
"""

SAMPLE_DOMAIN_RULES = """
industries:
  - name: healthcare
    display_name: Healthcare
    description: Healthcare industry rules
    mandatory_logic: ["hipaa_compliance", "patient_data_encryption"]
    ux_patterns: ["accessibility_first"]
    compliance_requirements: ["HIPAA"]
    business_invariants: ["patient_consent_required"]
  - name: fintech
    display_name: Financial Technology
    description: Fintech industry rules
    mandatory_logic: ["pci_compliance", "audit_trail"]
    compliance_requirements: ["PCI-DSS"]
"""

SAMPLE_VALIDATION_GATES = """
global_checks:
  - id: no_hardcoded_secrets
    category: security
    rule: "No hardcoded secrets"
    action: regex_search_keys
    severity: critical
    auto_fix: false
  - id: no_eval_usage
    category: security
    rule: "No eval() or exec() usage"
    action: check_eval
    severity: critical
    auto_fix: false
    pattern: "\\\\b(eval|exec)\\\\s*\\\\("
  - id: every_function_must_have_docstring
    category: quality
    rule: "Every function must have a docstring"
    action: lint_check
    severity: warning
domain_specific_checks:
  - domain: healthcare
    checks:
      - id: hipaa_data_encryption
        rule: "PHI must be encrypted"
        action: check_encryption
        severity: critical
"""

SAMPLE_GLOSSARY = """
transformation_rules:
  technical_to_corporate:
    - from: "refactor"
      to: "optimize"
      context: "code improvement"
  error_messages:
    - original: "NullPointerException"
      polished: "Unexpected value encountered"
  feature_descriptions:
    - technical: "auto_scaling"
      marketing: "Elastic Capacity"
      benefit: "Automatically adapts to demand"
  communication_templates:
    - name: "status_update"
      template: "Progress update: ..."
  status_descriptions:
    - technical: "build_failed"
      client_facing: "Setup requires attention"
"""


# ============================================================
#  Fixtures (also in test_dna_parts/conftest.py for direct sub-module runs)
# ============================================================

@pytest.fixture
def dna_loader(tmp_path):
    """Create a DNALoader with a temporary DNA root directory."""
    return DNALoader(dna_root=str(tmp_path))


@pytest.fixture
def dna_root_with_files(tmp_path):
    """Create a DNA root directory with sample YAML files."""
    dna_dir = tmp_path / "dna"
    dna_dir.mkdir()
    return dna_dir


@pytest.fixture
def populated_dna_loader(tmp_path):
    """Create a DNALoader with sample YAML files written to disk."""
    dna_dir = tmp_path / "dna"
    dna_dir.mkdir()

    if YAML_AVAILABLE:
        (dna_dir / "logic_modules.yaml").write_text(SAMPLE_LOGIC_MODULES, encoding="utf-8")
        (dna_dir / "domain_expert_rules.yaml").write_text(SAMPLE_DOMAIN_RULES, encoding="utf-8")
        (dna_dir / "validation_gates.yaml").write_text(SAMPLE_VALIDATION_GATES, encoding="utf-8")
        (dna_dir / "professional_glossary.yaml").write_text(SAMPLE_GLOSSARY, encoding="utf-8")

    loader = DNALoader(dna_root=str(dna_dir))
    return loader


from .test_dna_parts import *  # noqa: F401,F403
