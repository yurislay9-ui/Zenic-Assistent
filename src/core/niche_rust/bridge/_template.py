"""
Niche Rust Bridge — NicheTemplate class.

YAML template generation and validation system.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ._native import NATIVE_AVAILABLE, _native

logger = logging.getLogger(__name__)


class NicheTemplate:
    """YAML template generation and validation system.

    Generates a structured template skeleton from a NicheDefinition,
    validates completeness, and tracks missing fields for the
    interactive data collection agent.

    Usage::

        tmpl = NicheTemplate()

        # Generate a template from a niche
        template = tmpl.generate("telemedicine")

        # Fill a field
        tmpl.set_field(template, "business_identity", "business_name", "My Clinic")

        # Validate
        result = tmpl.validate(template)

        # List missing fields
        missing = tmpl.missing_fields(template)

        # Export to YAML
        yaml_str = tmpl.to_yaml(template)
    """

    def generate(self, niche_id: str) -> Optional[Dict[str, Any]]:
        """Generate a YAML template skeleton from a niche_id."""
        if not niche_id or not isinstance(niche_id, str):
            logger.error("NicheTemplate.generate: niche_id must be a non-empty string")
            return None
        if not NATIVE_AVAILABLE:
            logger.warning("NicheTemplate.generate: Rust extension not available")
            return None
        return _native.template_generate(niche_id)

    def generate_from_niche(self, niche: Any) -> Optional[Dict[str, Any]]:
        """Generate a template from an existing NicheDefinition object."""
        if niche is None:
            logger.error("NicheTemplate.generate_from_niche: niche cannot be None")
            return None
        if not NATIVE_AVAILABLE:
            logger.warning("NicheTemplate.generate_from_niche: Rust extension not available")
            return None
        try:
            return _native.template_generate_from_niche(niche)
        except Exception as e:
            logger.error("NicheTemplate.generate_from_niche: %s", e)
            return None

    def validate(self, template_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Validate a template dict for completeness."""
        _incomplete = {
            "valid": False,
            "total_fields": 0,
            "filled_fields": 0,
            "missing_required": 0,
            "completion_pct": 0.0,
            "status": "incomplete",
            "missing_field_names": [],
        }
        if not template_dict:
            return _incomplete
        if not NATIVE_AVAILABLE:
            logger.warning("NicheTemplate.validate: Rust extension not available")
            return {**_incomplete, "error": "Rust extension not available"}
        try:
            return _native.template_validate(template_dict)
        except Exception as e:
            logger.error("NicheTemplate.validate: %s", e)
            return {**_incomplete, "error": str(e)}

    def missing_fields(self, template_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """List all missing required fields in a template."""
        if not template_dict:
            return []
        if not NATIVE_AVAILABLE:
            logger.warning("NicheTemplate.missing_fields: Rust extension not available")
            return []
        try:
            return _native.template_missing_fields(template_dict)
        except Exception as e:
            logger.error("NicheTemplate.missing_fields: %s", e)
            return []

    def set_field(
        self,
        template_dict: Dict[str, Any],
        section_id: str,
        field_name: str,
        value: Any,
    ) -> bool:
        """Fill a field value in a template dict."""
        if not template_dict:
            logger.error("NicheTemplate.set_field: template_dict is empty")
            return False
        if not section_id or not field_name:
            logger.error("NicheTemplate.set_field: section_id and field_name required")
            return False
        if not NATIVE_AVAILABLE:
            logger.warning("NicheTemplate.set_field: Rust extension not available")
            return False
        try:
            return _native.template_set_field(
                template_dict, section_id, field_name, value
            )
        except Exception as e:
            logger.error("NicheTemplate.set_field: %s", e)
            return False

    def to_yaml(self, template_dict: Dict[str, Any]) -> Optional[str]:
        """Serialize a template dict to a YAML string."""
        if not template_dict:
            return None
        if not NATIVE_AVAILABLE:
            logger.warning("NicheTemplate.to_yaml: Rust extension not available")
            return None
        try:
            return _native.template_to_yaml(template_dict)
        except Exception as e:
            logger.error("NicheTemplate.to_yaml: %s", e)
            return None
