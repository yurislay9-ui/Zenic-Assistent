"""Mixin: YAML loading methods for NicheLoader."""

import os

from ._imports import logger, YAML_AVAILABLE, NicheTemplate


class LoadingMixin:
    """Mixin providing YAML niche template loading."""

    def load_all(self) -> int:
        """
        Carga todas las plantillas YAML de nichos.

        Returns:
            Numero de nichos cargados
        """
        if not YAML_AVAILABLE:
            logger.warning("NicheLoader: PyYAML not available, cannot load niche templates")
            return 0

        if not os.path.isdir(self._root):
            logger.warning(f"NicheLoader: Niche root not found: {self._root}")
            return 0

        count = 0
        for root, dirs, files in os.walk(self._root):
            for f in files:
                if f.endswith(".yaml") or f.endswith(".yml"):
                    path = os.path.join(root, f)
                    try:
                        niche = self._load_yaml(path)
                        if niche:
                            self._niches[niche.name] = niche
                            # Index by domain
                            self._domain_index.setdefault(niche.domain, []).append(niche.name)
                            count += 1
                    except Exception as e:
                        logger.error(f"NicheLoader: Error loading {path}: {e}")

        self._loaded = True
        logger.info(f"NicheLoader: Loaded {count} niche templates from {self._root}")
        return count

    def _load_yaml(self, path: str):
        """Carga un archivo YAML de nicho."""
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "niche" not in data:
            logger.warning(f"NicheLoader: Invalid niche YAML (missing 'niche' key): {path}")
            return None

        niche_data = data["niche"]
        comp_data = data.get("composition", {})
        entities_data = data.get("entities", [])
        workflow_data = data.get("workflow", {})
        features_data = data.get("features", {})
        risk_data = data.get("risk_assessment", {})

        # Parse triggers from "trigger:description" format
        triggers = []
        for t in workflow_data.get("triggers", []):
            triggers.append(str(t))

        return NicheTemplate(
            name=niche_data.get("name", ""),
            domain=niche_data.get("domain", ""),
            subdomain=niche_data.get("subdomain", ""),
            description=niche_data.get("description", ""),
            scale=niche_data.get("scale", "medium"),

            base_template=comp_data.get("base_template", "apps/base"),
            app_template=comp_data.get("app_template", ""),
            blocks=comp_data.get("blocks", []),
            variables=comp_data.get("variables", {}),

            entities=entities_data,

            typical_paths=workflow_data.get("typical_paths", []),
            triggers=triggers,

            core_features=features_data.get("core", []),
            advanced_features=features_data.get("advanced", []),
            optional_features=features_data.get("optional", []),

            data_sensitivity=risk_data.get("data_sensitivity", "medium"),
            compliance=risk_data.get("compliance", []),
            backup_frequency=risk_data.get("backup_frequency", "daily"),
            access_control=risk_data.get("access_control", "basic"),
            audit_trail=risk_data.get("audit_trail", False),

            yaml_path=path,
        )
