"""
Zenic-Agents Asistente - Blueprint Loader (Phase 5)

Loads certified Blueprints from:
  - YAML/JSON files (signed or unsigned)
  - Python dictionaries
  - Niche YAML templates (via converter)

Supports:
  - Single Blueprint loading
  - Directory scanning (batch loading)
  - Signed Blueprint verification
  - Legacy Blueprint (Phase 3) compatibility
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from .types import (
    ActionTemplateDef, BlueprintCompatibility, BlueprintMetadataV2,
    BlueprintSignature, BlueprintStatus, BlueprintTier,
    BusinessRuleDef, DBEntitySchema, DBFieldSchema, DBSchema,
    FieldType, MonitorHook,
)
from .schema import CertifiedBlueprint
from .certifier import verify_blueprint

logger = logging.getLogger(__name__)

# Try YAML support
try:
    import yaml as _yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ──────────────────────────────────────────────────────────────
#  BLUEPRINT LOADER
# ──────────────────────────────────────────────────────────────

class BlueprintLoaderV2:
    """Loads CertifiedBlueprint objects from various sources.

    Usage:
        loader = BlueprintLoaderV2()

        # From a YAML file
        bp = loader.load_file("blueprints/retail.yaml")

        # From a directory
        bps = loader.load_directory("blueprints/")

        # From a dict
        bp = loader.load_dict(data)
    """

    def load_file(self, filepath: str, verify: bool = True) -> Optional[CertifiedBlueprint]:
        """Load a Blueprint from a YAML or JSON file.

        Args:
            filepath: Path to the Blueprint file.
            verify: Whether to verify ECDSA signature if present.

        Returns:
            CertifiedBlueprint or None if loading failed.
        """
        if not os.path.isfile(filepath):
            logger.error("BlueprintLoader: File not found: %s", filepath)
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            logger.error("BlueprintLoader: Cannot read %s: %s", filepath, e)
            return None

        # Parse based on extension
        if filepath.endswith((".yaml", ".yml")):
            data = self._parse_yaml(content)
        elif filepath.endswith(".json"):
            data = json.loads(content)
        else:
            # Try YAML first, then JSON
            data = self._parse_yaml(content) or self._parse_json(content)

        if data is None:
            logger.error("BlueprintLoader: Failed to parse %s", filepath)
            return None

        blueprint = self.load_dict(data)
        if blueprint is None:
            return None

        # Verify signature if present
        if verify and blueprint.is_certified:
            if not verify_blueprint(blueprint):
                logger.warning(
                    "BlueprintLoader: Signature verification FAILED for %s",
                    blueprint.metadata.name,
                )
                blueprint.metadata.status = BlueprintStatus.DRAFT

        return blueprint

    def load_directory(
        self, dirpath: str, verify: bool = True,
    ) -> List[CertifiedBlueprint]:
        """Load all Blueprint files from a directory.

        Scans for .yaml, .yml, and .json files.
        Returns list of successfully loaded Blueprints.
        """
        blueprints: List[CertifiedBlueprint] = []

        if not os.path.isdir(dirpath):
            logger.warning("BlueprintLoader: Directory not found: %s", dirpath)
            return blueprints

        for filename in sorted(os.listdir(dirpath)):
            if not filename.endswith((".yaml", ".yml", ".json")):
                continue
            filepath = os.path.join(dirpath, filename)
            bp = self.load_file(filepath, verify=verify)
            if bp is not None:
                blueprints.append(bp)

        logger.info(
            "BlueprintLoader: Loaded %d Blueprints from %s",
            len(blueprints), dirpath,
        )
        return blueprints

    def load_dict(self, data: Dict[str, Any]) -> Optional[CertifiedBlueprint]:
        """Load a CertifiedBlueprint from a dictionary.

        Expected format:
        {
            "metadata": { "name": "...", "version": "...", ... },
            "db_schema": { "entities": [...] },
            "executors": { ... },
            "rules": [...],
            "actions": { ... },
            "monitors": { ... }
        }
        """
        try:
            metadata = self._parse_metadata(data.get("metadata", {}))
            db_schema = self._parse_db_schema(data.get("db_schema", {}))
            executor_schemas = data.get("executors", {})
            rules = self._parse_rules(data.get("rules", []))
            actions = self._parse_actions(data.get("actions", {}))
            monitor_hooks = self._parse_monitor_hooks(data.get("monitors", {}))

            return CertifiedBlueprint(
                metadata=metadata,
                db_schema=db_schema,
                executor_schemas=executor_schemas,
                rules=rules,
                actions=actions,
                monitor_hooks=monitor_hooks,
            )
        except Exception as e:
            logger.error("BlueprintLoader: Failed to parse dict: %s", e)
            return None

    # ── Parsing Helpers ────────────────────────────────────

    def _parse_metadata(self, data: Dict[str, Any]) -> BlueprintMetadataV2:
        """Parse metadata section."""
        signature = None
        sig_data = data.get("signature")
        if sig_data and isinstance(sig_data, dict):
            signature = BlueprintSignature(
                algorithm=sig_data.get("algorithm", "ECDSA-P256"),
                signature_hex=sig_data.get("signature_hex", ""),
                public_key_hex=sig_data.get("public_key_hex", ""),
                signed_at=sig_data.get("signed_at", 0.0),
                signer_id=sig_data.get("signer_id", ""),
                certificate_id=sig_data.get("certificate_id", ""),
            )

        compatibility = []
        for c_data in data.get("compatibility", []):
            compatibility.append(BlueprintCompatibility(
                blueprint_name=c_data.get("blueprint_name", ""),
                version_range=c_data.get("version_range", "*"),
                composition_notes=c_data.get("composition_notes", ""),
                known_conflicts=c_data.get("known_conflicts", []),
            ))

        tier_str = data.get("tier", "free")
        status_str = data.get("status", "draft")

        return BlueprintMetadataV2(
            name=data.get("name", "unnamed"),
            version=data.get("version", "1.0.0"),
            domain=data.get("domain", ""),
            subdomain=data.get("subdomain", ""),
            description=data.get("description", ""),
            author=data.get("author", ""),
            tier=BlueprintTier(tier_str),
            status=BlueprintStatus(status_str),
            signature=signature,
            compatibility=compatibility,
            tags=data.get("tags", []),
            icon=data.get("icon", ""),
            scale=data.get("scale", "medium"),
        )

    def _parse_db_schema(self, data: Dict[str, Any]) -> DBSchema:
        """Parse database schema section."""
        entities = []
        for e_data in data.get("entities", []):
            fields = []
            for f_data in e_data.get("fields", []):
                ft_str = f_data.get("type", "str")
                try:
                    ft = FieldType(ft_str)
                except ValueError:
                    ft = FieldType.STR
                fields.append(DBFieldSchema(
                    name=f_data.get("name", ""),
                    field_type=ft,
                    required=f_data.get("required", True),
                    unique=f_data.get("unique", False),
                    indexed=f_data.get("indexed", False),
                    default=f_data.get("default"),
                    description=f_data.get("description", ""),
                ))
            entities.append(DBEntitySchema(
                name=e_data.get("name", ""),
                fields=fields,
                primary_key=e_data.get("primary_key", "id"),
                indexes=e_data.get("indexes", []),
                constraints=e_data.get("constraints", []),
                description=e_data.get("description", ""),
            ))

        return DBSchema(
            entities=entities,
            migrations=data.get("migrations", []),
            version=data.get("version", "1.0.0"),
        )

    def _parse_rules(self, data: List[Any]) -> List[BusinessRuleDef]:
        """Parse business rules section."""
        rules = []
        for r_data in data:
            if not isinstance(r_data, dict):
                continue
            rules.append(BusinessRuleDef(
                rule_id=r_data.get("rule_id", r_data.get("name", "")),
                name=r_data.get("name", ""),
                description=r_data.get("description", ""),
                executor_type=r_data.get("executor_type", ""),
                condition=r_data.get("condition", ""),
                action=r_data.get("action", ""),
                severity=r_data.get("severity", "warning"),
                active=r_data.get("active", True),
            ))
        return rules

    def _parse_actions(self, data: Dict[str, Any]) -> List[ActionTemplateDef]:
        """Parse action templates section."""
        actions = []
        for key, a_data in data.items():
            if not isinstance(a_data, dict):
                continue
            actions.append(ActionTemplateDef(
                template_id=key,
                name=a_data.get("name", key),
                description=a_data.get("description", ""),
                executor_type=a_data.get("executor_type", ""),
                config_template=a_data.get("config", {}),
                safety_category=a_data.get("safety_category", "moderate"),
                requires_confirmation=a_data.get("requires_confirmation", False),
                requires_approval=a_data.get("requires_approval", False),
            ))
        return actions

    def _parse_monitor_hooks(self, data: Dict[str, Any]) -> List[MonitorHook]:
        """Parse monitor hooks section."""
        hooks = []
        for monitor_id, h_data in data.items():
            if not isinstance(h_data, dict):
                continue
            hooks.append(MonitorHook(
                monitor_id=monitor_id,
                weight=h_data.get("weight", "lightweight"),
                interval_seconds=float(h_data.get("interval_seconds", 300)),
                enabled=h_data.get("enabled", True),
                thresholds=h_data.get("thresholds", []),
                params=h_data.get("params", {}),
                notification_channel=h_data.get("notification_channel", "log"),
            ))
        return hooks

    def _parse_yaml(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse YAML content."""
        if not _HAS_YAML:
            return None
        try:
            return _yaml.safe_load(content)
        except Exception:
            return None

    def _parse_json(self, content: str) -> Optional[Dict[str, Any]]:
        """Parse JSON content."""
        try:
            return json.loads(content)
        except Exception:
            return None
