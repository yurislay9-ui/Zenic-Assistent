"""
POST endpoint mixin for ZenicHTTPHandler.
"""

from ._shared import (
    logger, json, _run_async, _REQUEST_TIMEOUT,
    build_normal_response, build_partial_reasoning_response,
    build_error_response, build_overloaded_response,
    build_artifact_response,
    _OPEN_DESIGN_AVAILABLE, _extract_msg_text,
)

from ._core_mixin import PostMixinCoreMixin
from ._extra_mixin import PostMixinExtraMixin

__all__ = ["PostMixin"]


class PostMixin(PostMixinCoreMixin, PostMixinExtraMixin):
    """See module docstring."""
    pass
