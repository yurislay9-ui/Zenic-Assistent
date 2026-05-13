"""CodeTransformer main class combining all mixins."""

from .refactor import RefactorMixin
from .fixer import FixerMixin
from .optimizer import OptimizerMixin


class CodeTransformer(
    RefactorMixin,
    FixerMixin,
    OptimizerMixin,
):
    """Transforms code through refactoring, fixing, and optimization."""
