'''sidecar - refactored into sub-modules.'''

from ._types import _MiddlewareContext
from ._core import Sidecar, sidecar_decorator

__all__ = ['_MiddlewareContext', 'Sidecar', 'sidecar_decorator']
