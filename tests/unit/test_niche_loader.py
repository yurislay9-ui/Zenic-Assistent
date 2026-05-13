"""
Unit tests for NicheLoader

Tests loading of YAML niche templates, pattern matching / search,
domain filtering, compliance filtering, and cross-niche analysis.
"""

import os
import pytest

from src.core.niche_loader import (
    NicheLoader, NicheTemplate, NICHE_ROOT, YAML_AVAILABLE,
    get_niche_loader,
)


# ============================================================
#  Sample Data (shared with sub-modules)
# ============================================================

SAMPLE_NICHE_YAML = """
niche:
  name: clinic_management
  domain: healthcare
  subdomain: clinic
  description: Clinic management system with appointments and patient records
  scale: medium

composition:
  base_template: apps/base
  app_template: apps/fastapi_app
  blocks:
    - jwt_auth
    - crud_service
    - email_smtp
    - task_scheduler
  variables:
    project_name: clinic_app

entities:
  - name: Patient
    fields:
      - name: name
        type: str
      - name: email
        type: str
  - name: Appointment
    fields:
      - name: date
        type: datetime
      - name: status
        type: str

workflow:
  typical_paths:
    - "Patient → Create Appointment → Notify"
  triggers:
    - "appointment_created:Send confirmation email"

features:
  core:
    - Patient management
    - Appointment scheduling
  advanced:
    - Email notifications
  optional:
    - SMS reminders

risk_assessment:
  data_sensitivity: high
  compliance:
    - HIPAA
    - GDPR
  backup_frequency: hourly
  access_control: rbac
  audit_trail: true
"""

SAMPLE_NICHE_YAML_2 = """
niche:
  name: restaurant_pos
  domain: hospitality
  subdomain: restaurant
  description: Restaurant point of sale and inventory management
  scale: small

composition:
  base_template: apps/base
  blocks:
    - crud_service
    - inventory_tracker
    - stripe_payments

entities:
  - name: MenuItem
    fields:
      - name: name
        type: str
      - name: price
        type: float

workflow:
  typical_paths: []
  triggers: []

features:
  core:
    - Order management
  advanced: []
  optional: []

risk_assessment:
  data_sensitivity: low
  compliance: []
  backup_frequency: daily
  access_control: basic
  audit_trail: false
"""


# ============================================================
#  Fixtures (shared with sub-modules)
# ============================================================

@pytest.fixture
def niche_dir(tmp_path):
    """Create a niche directory structure with sample YAML files."""
    domains = tmp_path / "niches"
    healthcare = domains / "healthcare"
    healthcare.mkdir(parents=True)
    hospitality = domains / "hospitality"
    hospitality.mkdir(parents=True)

    if YAML_AVAILABLE:
        (healthcare / "clinic.yaml").write_text(SAMPLE_NICHE_YAML, encoding="utf-8")
        (hospitality / "restaurant.yaml").write_text(SAMPLE_NICHE_YAML_2, encoding="utf-8")

    return domains


@pytest.fixture
def niche_loader(niche_dir):
    """Create a NicheLoader pointing at the temp niche directory."""
    return NicheLoader(niche_root=str(niche_dir))


@pytest.fixture
def loaded_niche_loader(niche_loader):
    """Create and load a NicheLoader with sample data."""
    if not YAML_AVAILABLE:
        pytest.skip("PyYAML not available")
    niche_loader.load_all()
    return niche_loader


from .test_niche_parts import *  # noqa: F401,F403
