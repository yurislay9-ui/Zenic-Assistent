"""
ZENIC-AGENTS v16 — Open Design Integration Module

This module provides the bridge between ZENIC-AGENTS and Open Design,
enabling a symbiotic architecture where:

- Open Design acts as the visual orchestrator (Frontend)
- ZENIC-AGENTS acts as the generative AI engine (Backend)

Integration capabilities:
1. SSE Streaming — real-time chunk delivery for Open Design's iframe
2. Artifact wrapping — <artifact>...</artifact> XML tags for code delivery
3. Visual bypass routing — skip SMT/AC-3 for UI generation requests
4. Design System preservation — bypass ContextAgent truncation for DS prompts
5. CORS configuration — allow Open Design origins on both servers
"""

from .config import OpenDesignConfig, get_open_design_config
from .detector import OpenDesignDetector, is_open_design_request
from .artifact_builder import ArtifactBuilder, wrap_in_artifact
from .sse_streamer import SSEStreamer, create_sse_response

__all__ = [
    "OpenDesignConfig",
    "get_open_design_config",
    "OpenDesignDetector",
    "is_open_design_request",
    "ArtifactBuilder",
    "wrap_in_artifact",
    "SSEStreamer",
    "create_sse_response",
]
