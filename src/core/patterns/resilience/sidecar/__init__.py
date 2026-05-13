'''sidecar - refactored into sub-modules.'''

from ._core import _MiddlewareContext, Sidecar, sidecar_decorator

__all__ = ['_MiddlewareContext', 'Sidecar', 'sidecar_decorator']
