"""
Layer 4: Code Operations — Single-Responsibility Agents.

Each agent handles EXACTLY ONE code operation task.
All agents are 100% deterministic. No AI calls.

Agents:
    A17 CodeGenerator       — Generate code from templates
    A18 CodeRefactorer      — Refactor/transform existing code
    A19 CodeOptimizer       — Optimize code for performance
    A20 CodeFixer           — Fix bugs and errors
    A21 ProjectScaffolder   — Generate project scaffolding
    A22 DefensiveInjector   — Inject defensive code patterns
"""

from .code_generator import CodeGenerator
from .code_refactorer import CodeRefactorer
from .code_optimizer import CodeOptimizer
from .code_fixer import CodeFixer
from .project_scaffolder import ProjectScaffolder
from .defensive_injector import DefensiveInjector

__all__ = [
    "CodeGenerator",
    "CodeRefactorer",
    "CodeOptimizer",
    "CodeFixer",
    "ProjectScaffolder",
    "DefensiveInjector",
]
