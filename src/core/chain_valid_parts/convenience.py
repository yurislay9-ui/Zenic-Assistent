"""
Convenience functions for chain validation and execution.
"""

from typing import Any, Dict, Optional

from ._imports import (
    ValidationLevel, ValidationResult, RecoveryAction, ChainResult,
)
from .validator import ChainValidator
from .executor import ChainExecutor


def validate_chain(chain: Any, initial_data: Optional[Dict[str, Any]] = None,
                   context: Optional[Dict[str, Any]] = None,
                   level: ValidationLevel = ValidationLevel.STANDARD) -> ValidationResult:
    """Quick validation of a LogicChain."""
    validator = ChainValidator(level=level)
    return validator.validate(chain, initial_data or {}, context or {})


def execute_chain_safe(chain: Any, initial_data: Optional[Dict[str, Any]] = None,
                       context: Optional[Dict[str, Any]] = None,
                       recovery: RecoveryAction = RecoveryAction.SKIP,
                       max_retries: int = 1) -> ChainResult:
    """Execute a LogicChain with safety guarantees."""
    executor = ChainExecutor(default_recovery=recovery, max_retries=max_retries)
    return executor.execute(chain, initial_data or {}, context or {})
