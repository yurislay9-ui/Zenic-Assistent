"""Validation Gates — Modular YAML loader.

Quality validation rules are split across sub-files for maintainability.
Use load_all_gates() to get the assembled data.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_DIR = Path(__file__).parent


def load_all_gates() -> dict[str, Any]:
    """Load and merge all validation gate YAML fragments.

    Returns a dict with keys 'global_checks' and 'domain_specific_checks',
    identical to loading the original single-file validation_gates.yaml.
    """
    global_checks: list[dict[str, Any]] = []
    domain_checks: list[dict[str, Any]] = []
    for fragment in sorted(_DIR.glob("_*.yaml")):
        data = yaml.safe_load(fragment.read_text(encoding="utf-8"))
        global_checks.extend(data.get("global_checks", []))
        domain_checks.extend(data.get("domain_specific_checks", []))
    return {"global_checks": global_checks, "domain_specific_checks": domain_checks}
