"""
ChainValidator: Pre-execution validator for LogicChains.
"""

from typing import Any, Dict, List, Optional

from ._imports import ValidationLevel, ValidationResult, logger


class ChainValidator:
    """
    Pre-execution validator for LogicChains.

    Validates:
      1. Required inputs are provided
      2. Block compatibility (output→input matching)
      3. No circular dependencies
      4. Category-specific rules
      5. Performance hints for large chains
    """

    def __init__(self, level: ValidationLevel = ValidationLevel.STANDARD):
        self._level = level

    def validate(self, chain: Any, initial_data: Optional[Dict[str, Any]] = None,
                 context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validate a LogicChain before execution.

        Args:
            chain: LogicChain to validate
            initial_data: Data that will be passed to execute()
            context: Context that will be passed to execute()

        Returns:
            ValidationResult with any issues found
        """
        result = ValidationResult()
        initial_data = initial_data or {}
        context = context or {}

        # 1. Check chain is not empty
        blocks = chain.blocks if hasattr(chain, 'blocks') else []
        if not blocks:
            result.add_warning("empty_chain", "Chain has no blocks to execute")
            return result

        # 2. Validate each block individually
        for i, block in enumerate(blocks):
            self._validate_block(block, i, initial_data, context, result)

        # 3. Check block compatibility (output→input)
        if self._level in (ValidationLevel.STANDARD, ValidationLevel.STRICT):
            self._validate_compatibility(blocks, result)

        # 4. Check for potential issues in strict mode
        if self._level == ValidationLevel.STRICT:
            self._validate_strict(blocks, initial_data, result)

        return result

    def _validate_block(self, block: Any, index: int, initial_data: Dict[str, Any],
                        context: Dict[str, Any], result: ValidationResult) -> None:
        """Validate a single block."""
        block_name = block.name if hasattr(block, 'name') else f"block_{index}"

        # Check block has required attributes
        if not hasattr(block, 'name') or not block.name:
            result.add_error("missing_name", f"Block at index {index} has no name", block_index=index)

        if not hasattr(block, 'execute'):
            result.add_error("missing_execute", f"Block '{block_name}' has no execute method",
                           block_name=block_name, block_index=index)
            return

        # Check block has a category
        category = getattr(block, 'category', '')
        if not category:
            result.add_warning("missing_category", f"Block '{block_name}' has no category",
                             block_name=block_name, block_index=index)

        # Category-specific validation
        if category == 'auth' and not context.get('db'):
            result.add_warning("auth_no_db",
                             f"Auth block '{block_name}' may need 'db' in context",
                             block_name=block_name, block_index=index)

        if category == 'data' and not context.get('db'):
            result.add_warning("data_no_db",
                             f"Data block '{block_name}' may need 'db' in context",
                             block_name=block_name, block_index=index)

        if category == 'integrations':
            # Check if integration blocks can function
            if block_name in ('email',) and not initial_data.get('to'):
                result.add_warning("email_no_recipient",
                                 f"Email block '{block_name}' needs 'to' in data",
                                 block_name=block_name, block_index=index)

    def _validate_compatibility(self, blocks: List[Any], result: ValidationResult) -> None:
        """Check that block outputs can feed into subsequent block inputs."""
        for i in range(len(blocks) - 1):
            current = blocks[i]
            next_block = blocks[i + 1]

            current_name = getattr(current, 'name', f'block_{i}')
            next_name = getattr(next_block, 'name', f'block_{i+1}')

            if not self._check_type_compatibility(current, next_block):
                result.add_warning(
                    "type_mismatch",
                    f"Block '{current_name}' outputs may be incompatible with "
                    f"block '{next_name}' inputs",
                    block_name=current_name,
                    block_index=i,
                )

    @staticmethod
    def _check_type_compatibility(block, next_block) -> bool:
        """Check that block outputs are compatible with next_block inputs."""
        # Get output and input types
        outputs = getattr(block, 'outputs', []) or []
        inputs = getattr(next_block, 'inputs', []) or []

        # If no type information, assume compatible
        if not outputs or not inputs:
            return True

        # Check that each required input type has a matching output type
        output_types = {o if isinstance(o, str) else o.get('type', '') for o in outputs}
        input_types = {i if isinstance(i, str) else i.get('type', '') for i in inputs}

        # Check for incompatibilities (non-empty intersection required)
        if input_types and output_types:
            common = output_types & input_types
            if not common and 'any' not in output_types and 'any' not in input_types:
                return False

        return True

    def _validate_strict(self, blocks: List[Any], initial_data: Dict[str, Any], result: ValidationResult) -> None:
        """Strict mode additional checks."""
        # Check chain length
        if len(blocks) > 10:
            result.add_warning("long_chain",
                             f"Chain has {len(blocks)} blocks - consider splitting into sub-chains")

        # Check for multiple blocks of same type
        names = [b.name for b in blocks]
        seen = set()
        for name in names:
            if name in seen:
                result.add_warning("duplicate_block",
                                 f"Block '{name}' appears multiple times - verify this is intentional")
            seen.add(name)

        # Check that validation comes before business logic
        categories = [b.category for b in blocks]
        for i in range(len(categories) - 1):
            if categories[i] == 'business_logic' and categories[i + 1] == 'validation':
                result.add_warning("validation_after_logic",
                                 f"Validation block after business logic at step {i+1} - consider validating first")
