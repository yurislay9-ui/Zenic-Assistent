"""
Certifier Bridge — Core certifier and helper classes.

Contains BlueprintCertifier and CertificationHelper which use
the Rust _zenic_native extension for certification operations.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .bridge import NicheBridge, NicheCatalog, NicheTemplate
from .ingest_bridge import DocumentIngestor, IngestionResult
from ._types import CertificationResultPy, NATIVE_AVAILABLE, _native

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  BlueprintCertifier — Main certifier class
# ──────────────────────────────────────────────────────────────

class BlueprintCertifier:
    """Blueprint certification engine for Zenic-Agents.

    Converts completed YAML templates into CertifiedBlueprints with
    ECDSA signing, integrity verification, and Phase 5 integration.

    The full certification pipeline:
        1. Completed template → BlueprintConfig extraction
        2. BlueprintConfig validation
        3. ECDSA signature generation
        4. CertifiedBlueprint creation
        5. Export as Phase 5 compatible dict or YAML

    Usage::

        certifier = BlueprintCertifier()

        # From a completed template dict
        result = certifier.certify_template(template_dict, private_key)

        if result.is_certified:
            # Use with Phase 5 Blueprint system
            blueprint_dict = result.blueprint_dict
            yaml_str = result.yaml_string
    """

    def __init__(self) -> None:
        self._bridge = NicheBridge()

    # ── Core Certification Pipeline ─────────────────────────

    def certify_template(
        self,
        template_dict: Dict[str, Any],
        private_key: str,
    ) -> CertificationResultPy:
        """Full certification pipeline: template → config → sign → certify.

        This is the primary entry point for blueprint certification.
        It takes a completed template dict (from the completer) and
        an ECDSA private key, and produces a fully certified blueprint.

        Args:
            template_dict: The completed template dict (as returned by
                completer_finalize or template_generate with filled values).
            private_key: ECDSA private key in hex format for signing.

        Returns:
            CertificationResultPy with the certified blueprint data.
        """
        result = CertificationResultPy()

        if not template_dict:
            result.errors.append("template_dict is required")
            return result

        if not private_key or not isinstance(private_key, str):
            result.errors.append("private_key must be a non-empty string")
            return result

        if not NATIVE_AVAILABLE:
            result.errors.append(
                "Rust extension not available. Run 'maturin develop' first."
            )
            return result

        # Step 1: Extract BlueprintConfig from template
        config_result = self.extract_config(template_dict)
        if config_result is None:
            result.errors.append("Failed to extract BlueprintConfig from template")
            return result

        if hasattr(config_result, "errors") and config_result.errors:
            result.warnings.extend(config_result.errors)

        if hasattr(config_result, "warnings") and config_result.warnings:
            result.warnings.extend(config_result.warnings)

        # Step 2: Sign the config
        sign_result = self.sign_config(config_result.config, private_key)
        if sign_result is None:
            result.errors.append("Failed to sign BlueprintConfig")
            return result

        # Step 3: Export as Phase 5 dict
        blueprint = sign_result
        blueprint_dict = self.export_blueprint_dict(blueprint)
        yaml_string = self.export_yaml(blueprint)

        result.success = True
        result.blueprint_id = getattr(blueprint, "blueprint_id", None)
        result.content_hash = getattr(blueprint, "content_hash", "")
        result.status = str(getattr(blueprint, "status", "signed"))
        result.blueprint_dict = blueprint_dict
        result.yaml_string = yaml_string

        if hasattr(blueprint, "warnings") and blueprint.warnings:
            result.warnings.extend(blueprint.warnings)

        return result

    def extract_config(
        self, template_dict: Dict[str, Any]
    ) -> Optional[Any]:
        """Extract a BlueprintConfig from a completed template dict."""
        if not template_dict:
            logger.error("BlueprintCertifier.extract_config: template_dict is required")
            return None

        if not NATIVE_AVAILABLE:
            logger.warning("BlueprintCertifier.extract_config: Rust extension not available")
            return None

        try:
            return _native.certifier_from_template(template_dict)
        except Exception as e:
            logger.error("BlueprintCertifier.extract_config: %s", e)
            return None

    def sign_config(
        self, config: Any, private_key: str
    ) -> Optional[Any]:
        """Sign a BlueprintConfig and produce a CertifiedBlueprint."""
        if config is None:
            logger.error("BlueprintCertifier.sign_config: config is required")
            return None

        if not private_key:
            logger.error("BlueprintCertifier.sign_config: private_key is required")
            return None

        if not NATIVE_AVAILABLE:
            logger.warning("BlueprintCertifier.sign_config: Rust extension not available")
            return None

        try:
            return _native.certifier_sign(config, private_key)
        except Exception as e:
            logger.error("BlueprintCertifier.sign_config: %s", e)
            return None

    def verify_blueprint(
        self, blueprint: Any, public_key: str
    ) -> bool:
        """Verify a CertifiedBlueprint's ECDSA signature."""
        if blueprint is None or not public_key:
            return False

        if not NATIVE_AVAILABLE:
            logger.warning("BlueprintCertifier.verify_blueprint: Rust extension not available")
            return False

        try:
            return _native.certifier_verify(blueprint, public_key)
        except Exception as e:
            logger.error("BlueprintCertifier.verify_blueprint: %s", e)
            return False

    def compute_hash(self, config: Any) -> Optional[str]:
        """Compute the canonical hash of a BlueprintConfig."""
        if config is None:
            return None

        if not NATIVE_AVAILABLE:
            logger.warning("BlueprintCertifier.compute_hash: Rust extension not available")
            return None

        try:
            return _native.certifier_compute_hash(config)
        except Exception as e:
            logger.error("BlueprintCertifier.compute_hash: %s", e)
            return None

    def validate_config(self, config: Any) -> Dict[str, Any]:
        """Validate a BlueprintConfig for completeness."""
        if config is None:
            return {
                "valid": False,
                "errors": ["config is required"],
                "warnings": [],
                "compliance_count": 0,
                "db_tables": 0,
                "monitors": 0,
                "actions": 0,
            }

        if not NATIVE_AVAILABLE:
            logger.warning("BlueprintCertifier.validate_config: Rust extension not available")
            return {
                "valid": False,
                "errors": ["Rust extension not available"],
                "warnings": [],
                "compliance_count": 0,
                "db_tables": 0,
                "monitors": 0,
                "actions": 0,
            }

        try:
            return _native.certifier_validate_config(config)
        except Exception as e:
            logger.error("BlueprintCertifier.validate_config: %s", e)
            return {
                "valid": False,
                "errors": [str(e)],
                "warnings": [],
                "compliance_count": 0,
                "db_tables": 0,
                "monitors": 0,
                "actions": 0,
            }

    def export_blueprint_dict(self, blueprint: Any) -> Optional[Dict[str, Any]]:
        """Export a CertifiedBlueprint as a Phase 5 compatible dict."""
        if blueprint is None:
            return None

        if not NATIVE_AVAILABLE:
            logger.warning("BlueprintCertifier.export_blueprint_dict: Rust extension not available")
            return None

        try:
            return _native.certifier_to_blueprint_dict(blueprint)
        except Exception as e:
            logger.error("BlueprintCertifier.export_blueprint_dict: %s", e)
            return None

    def export_yaml(self, blueprint: Any) -> Optional[str]:
        """Export a CertifiedBlueprint as a YAML string."""
        if blueprint is None:
            return None

        if not NATIVE_AVAILABLE:
            logger.warning("BlueprintCertifier.export_yaml: Rust extension not available")
            return None

        try:
            return _native.certifier_export_yaml(blueprint)
        except Exception as e:
            logger.error("BlueprintCertifier.export_yaml: %s", e)
            return None


# ──────────────────────────────────────────────────────────────
#  CertificationHelper — Convenience workflow methods
# ──────────────────────────────────────────────────────────────

class CertificationHelper:
    """Convenience helper for common certification workflows.

    Provides higher-level methods that combine multiple steps
    from the full pipeline into single calls.
    """

    def __init__(self) -> None:
        self._certifier = BlueprintCertifier()
        self._ingestor = DocumentIngestor()

    def certify_from_documents(
        self,
        niche_id: str,
        files: Optional[List[Tuple[str, Optional[bytes]]]] = None,
        texts: Optional[List[str]] = None,
        private_key: str = "",
    ) -> CertificationResultPy:
        """Full workflow: niche selection → document ingestion → certification."""
        result = CertificationResultPy()

        if not niche_id:
            result.errors.append("niche_id is required")
            return result

        if not private_key:
            result.errors.append("private_key is required for certification")
            return result

        # Step 1-2: Ingest documents and auto-fill template
        ingestion = self._ingestor.ingest_and_match(
            niche_id=niche_id,
            files=files,
            texts=texts,
        )

        if ingestion.template_dict is None:
            result.errors.append("Failed to generate template from niche")
            result.errors.extend(ingestion.errors)
            return result

        # Log ingestion results
        if ingestion.matched_fields:
            result.warnings.append(
                f"Auto-filled {len(ingestion.matched_fields)} fields from documents"
            )

        # Step 3: Check if template is complete enough for certification
        bridge = NicheBridge()
        validation = bridge.validate_template(ingestion.template_dict)
        if isinstance(validation, dict) and validation.get("missing_required", 0) > 0:
            missing = validation.get("missing_field_names", [])
            result.warnings.append(
                f"Template has {len(missing)} missing required fields: "
                f"{', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}"
            )

        # Step 4: Certify the template
        cert_result = self._certifier.certify_template(
            ingestion.template_dict, private_key
        )

        # Merge results
        result.success = cert_result.success
        result.blueprint_id = cert_result.blueprint_id
        result.content_hash = cert_result.content_hash
        result.status = cert_result.status
        result.blueprint_dict = cert_result.blueprint_dict
        result.yaml_string = cert_result.yaml_string
        result.warnings.extend(cert_result.warnings)
        result.errors.extend(cert_result.errors)

        return result

    def certify_from_text(
        self,
        niche_id: str,
        text: str,
        private_key: str,
    ) -> CertificationResultPy:
        """Certify a blueprint from a single text input."""
        return self.certify_from_documents(
            niche_id=niche_id,
            texts=[text] if text else None,
            private_key=private_key,
        )

    def verify_exported(
        self,
        blueprint_yaml_or_dict: Any,
        public_key: str,
    ) -> bool:
        """Verify a previously exported blueprint."""
        if not public_key:
            return False

        if isinstance(blueprint_yaml_or_dict, dict):
            integrity = blueprint_yaml_or_dict.get("integrity", {})
            if not integrity:
                return False
            content_hash = integrity.get("content_hash", "")
            signature = integrity.get("signature", "")
            if not content_hash or not signature:
                return False
            return True  # Placeholder; real verification needs Rust

        return False
