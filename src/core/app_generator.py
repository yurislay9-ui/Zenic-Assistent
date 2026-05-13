"""
ZENIC-AGENTS - AppGenerator (Facade)

Thin facade that re-exports all public symbols from the
app_gen_parts sub-package.  The original 1 297-line module has been
split into logical sub-modules; this file preserves the public API.

Import path unchanged:
    from src.core.app_generator import AppGenerator, GeneratedProject
"""

from src.core.app_gen_parts import (
    AppGenerator,
    GeneratedProject,
    PROJECTS_DIR,
    FileGeneratorMixin,
    ServiceGeneratorMixin,
    TemplateGeneratorMixin,
    UtilsMixin,
)

__all__ = [
    "AppGenerator",
    "GeneratedProject",
    "PROJECTS_DIR",
    "FileGeneratorMixin",
    "ServiceGeneratorMixin",
    "TemplateGeneratorMixin",
    "UtilsMixin",
]
