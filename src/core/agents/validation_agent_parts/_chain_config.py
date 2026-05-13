"""
ValidationAgent chain + config validation mixin.
"""

import logging
from typing import Any, List

from ._imports import (
    ValidationOutput, ValidationIssue,
    CHAIN_COMPATIBILITY_RULES,
    logger,
)


class ChainConfigValidationMixin:
    """Chain and config validation methods for ValidationAgent."""

    # ============================================================
    #  CHAIN VALIDATION (deterministic)
    # ============================================================

    def _validate_chain(self, chain_data: Any) -> ValidationOutput:
        """Validación determinista de cadenas lógicas."""
        issues = []

        # Parse chain data
        if isinstance(chain_data, str):
            try:
                import json
                chain = json.loads(chain_data)
            except Exception:
                chain = {"blocks": []}
        elif isinstance(chain_data, dict):
            chain = chain_data
        else:
            # Handle LogicChain objects
            chain = {
                "blocks": getattr(chain_data, 'blocks', []),
            }
            if hasattr(chain_data, '_blocks'):
                raw_blocks = chain_data._blocks
                chain["blocks"] = raw_blocks

        blocks = chain.get("blocks", [])
        if not blocks:
            return ValidationOutput(
                is_valid=True,
                issues=[ValidationIssue(
                    severity="info", code="empty_chain",
                    message="Chain has no blocks to execute",
                    suggestion="Add blocks to the chain",
                )],
                suggestions=["Consider adding processing blocks"],
                risk_score=0.0,
            )

        # Validate each block
        for i, block in enumerate(blocks):
            block_dict = block if isinstance(block, dict) else {}
            block_name = block_dict.get("name", getattr(block, 'name', f'block_{i}'))
            block_type = block_dict.get("type", getattr(block, 'category', ''))

            if not block_name or block_name == f'block_{i}':
                issues.append(ValidationIssue(
                    severity="warning", code="missing_name",
                    message=f"Block at index {i} has no name",
                    line=i,
                    suggestion="Give each block a descriptive name",
                ))

        # Check block compatibility
        if len(blocks) > 1:
            for i in range(len(blocks) - 1):
                current = blocks[i]
                next_block = blocks[i + 1]
                current_cat = self._get_block_category(current)
                next_cat = self._get_block_category(next_block)

                rule = CHAIN_COMPATIBILITY_RULES.get((current_cat, next_cat))
                if rule == "warning":
                    issues.append(ValidationIssue(
                        severity="info",
                        code="compatibility_hint",
                        message=f"Block {i} ({current_cat}) → Block {i+1} ({next_cat}): consider reordering",
                        line=i,
                        suggestion=f"Consider placing validation before {current_cat} blocks",
                    ))

        # Check chain length
        if len(blocks) > 10:
            issues.append(ValidationIssue(
                severity="info", code="long_chain",
                message=f"Chain has {len(blocks)} blocks - consider splitting",
                suggestion="Split into sub-chains for maintainability",
            ))

        risk_score = self._calculate_risk_score(issues)

        return ValidationOutput(
            is_valid=not any(i.severity == "error" for i in issues),
            issues=issues,
            suggestions=[f"Chain has {len(blocks)} blocks"] + [
                f"Fix: {i.message}" for i in issues if i.severity == "error"
            ],
            risk_score=risk_score,
        )

    # ============================================================
    #  CONFIG VALIDATION (deterministic)
    # ============================================================

    def _validate_config(self, config_data: Any) -> ValidationOutput:
        """Validación determinista de configuración."""
        issues = []

        if isinstance(config_data, str):
            try:
                import json
                config = json.loads(config_data)
            except Exception:
                # Try YAML
                try:
                    import yaml
                    config = yaml.safe_load(config_data) or {}
                except Exception:
                    issues.append(ValidationIssue(
                        severity="error", code="invalid_format",
                        message="Config is not valid JSON or YAML",
                        suggestion="Check syntax and format",
                    ))
                    return ValidationOutput(is_valid=False, issues=issues,
                                           risk_score=0.8)
        elif isinstance(config_data, dict):
            config = config_data
        else:
            config = {}

        # Check for common config issues
        if config.get("DEBUG") or config.get("debug"):
            issues.append(ValidationIssue(
                severity="info", code="debug_enabled",
                message="DEBUG mode is enabled - disable in production",
                suggestion="Set DEBUG=false for production",
            ))

        if config.get("SECRET_KEY") in ("change-this", "change-this-in-production", ""):
            issues.append(ValidationIssue(
                severity="error", code="weak_secret_key",
                message="Default SECRET_KEY detected - security risk",
                suggestion="Generate a strong secret key for production",
            ))

        risk_score = self._calculate_risk_score(issues)

        return ValidationOutput(
            is_valid=not any(i.severity == "error" for i in issues),
            issues=issues,
            suggestions=[i.suggestion for i in issues if i.suggestion],
            risk_score=risk_score,
        )
