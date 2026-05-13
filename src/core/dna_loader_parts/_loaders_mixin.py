"""
Loader methods mixin for DNALoader.
"""

import os
import logging
from typing import Dict, List

from ._imports import (
    logger, yaml, YAML_AVAILABLE,
    LogicModule, DomainRule, ValidationGate, GlossaryEntry,
)


class LoadersMixin:
    """Mixin with the four template loader methods."""

    # ================================================================
    #  LOADERS
    # ================================================================

    def _load_logic_modules(self) -> int:
        """Carga logic_modules.yaml."""
        path = os.path.join(self._root, "logic_modules.yaml")
        if not YAML_AVAILABLE or not os.path.isfile(path):
            return 0

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for mod_data in data.get("modules", []):
            mod = LogicModule(
                id=mod_data.get("id", ""),
                domain=mod_data.get("domain", ""),
                description=mod_data.get("description", ""),
                code_block=mod_data.get("code_block", ""),
                dependencies=mod_data.get("dependencies", []),
                verification_rule=mod_data.get("verification_rule", ""),
                inputs=mod_data.get("inputs", []),
                outputs=mod_data.get("outputs", []),
            )
            self._logic_modules[mod.id] = mod
            self._modules_by_domain.setdefault(mod.domain, []).append(mod.id)

        return len(self._logic_modules)

    def _load_domain_rules(self) -> int:
        """Carga domain_expert_rules.yaml."""
        path = os.path.join(self._root, "domain_expert_rules.yaml")
        if not YAML_AVAILABLE or not os.path.isfile(path):
            return 0

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        for ind_data in data.get("industries", []):
            rule = DomainRule(
                name=ind_data.get("name", ""),
                display_name=ind_data.get("display_name", ""),
                description=ind_data.get("description", ""),
                mandatory_logic=ind_data.get("mandatory_logic", []),
                ux_patterns=ind_data.get("ux_patterns", []),
                compliance_requirements=ind_data.get("compliance_requirements", []),
                business_invariants=ind_data.get("business_invariants", []),
                edge_cases=ind_data.get("edge_cases", []),
                suggested_entities=ind_data.get("suggested_entities", []),
                notification_triggers=ind_data.get("notification_triggers", []),
            )
            self._domain_rules[rule.name] = rule

        return len(self._domain_rules)

    def _load_validation_gates(self) -> int:
        """Carga validation_gates.yaml."""
        path = os.path.join(self._root, "validation_gates.yaml")
        if not YAML_AVAILABLE or not os.path.isfile(path):
            return 0

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Global checks
        for check_data in data.get("global_checks", []):
            gate = ValidationGate(
                id=check_data.get("id", ""),
                category=check_data.get("category", "quality"),
                rule=check_data.get("rule", ""),
                action=check_data.get("action", ""),
                severity=check_data.get("severity", "warning"),
                auto_fix=check_data.get("auto_fix", False),
                fix_strategy=check_data.get("fix_strategy", ""),
                pattern=check_data.get("pattern", ""),
            )
            self._validation_gates.append(gate)
            self._gates_by_category.setdefault(gate.category, []).append(gate.id)

        # Domain-specific checks
        for domain_data in data.get("domain_specific_checks", []):
            domain = domain_data.get("domain", "")
            domain_gates = []
            for check_data in domain_data.get("checks", []):
                gate = ValidationGate(
                    id=check_data.get("id", ""),
                    category="domain_specific",
                    rule=check_data.get("rule", ""),
                    action=check_data.get("action", ""),
                    severity=check_data.get("severity", "critical"),
                    auto_fix=check_data.get("auto_fix", False),
                    fix_strategy=check_data.get("fix_strategy", ""),
                    pattern=check_data.get("pattern", ""),
                    applies_to=check_data.get("applies_to", []),
                )
                self._validation_gates.append(gate)
                domain_gates.append(gate)
            self._domain_gates[domain] = domain_gates

        return len(self._validation_gates)

    def _load_glossary(self) -> int:
        """Carga professional_glossary.yaml."""
        path = os.path.join(self._root, "professional_glossary.yaml")
        if not YAML_AVAILABLE or not os.path.isfile(path):
            return 0

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        rules = data.get("transformation_rules", {})
        count = 0

        # Technical to corporate
        for entry in rules.get("technical_to_corporate", []):
            self._glossary.append(GlossaryEntry(
                from_term=entry.get("from", ""),
                to_term=entry.get("to", ""),
                context=entry.get("context", ""),
            ))
            count += 1

        # Error messages
        for entry in rules.get("error_messages", []):
            self._error_messages[entry.get("original", "")] = entry.get("polished", "")
            count += 1

        # Feature descriptions
        for entry in rules.get("feature_descriptions", []):
            self._feature_descriptions[entry.get("technical", "")] = {
                "marketing": entry.get("marketing", ""),
                "benefit": entry.get("benefit", ""),
            }
            count += 1

        # Communication templates
        self._communication_templates = rules.get("communication_templates", [])
        count += len(self._communication_templates)

        # Status descriptions
        for entry in rules.get("status_descriptions", []):
            self._glossary.append(GlossaryEntry(
                from_term=entry.get("technical", ""),
                to_term=entry.get("client_facing", ""),
                context="status",
            ))
            count += 1

        return count
