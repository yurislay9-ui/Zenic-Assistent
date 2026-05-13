"""
Open Design Integration Configuration.

Manages all configuration for the ZENIC-AGENTS ↔ Open Design bridge.
Reads from environment variables with sensible defaults for Termux/Android.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class OpenDesignConfig:
    """Configuration for Open Design integration.

    All values can be overridden via environment variables for flexibility
    in different deployment environments (Termux, VPS, Docker).
    """

    # ── Connection ──────────────────────────────────────────
    # Open Design typically runs on localhost:3000 in Termux
    open_design_origins: List[str] = field(default_factory=lambda: [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ])

    # ZENIC-AGENTS's own port (where Open Design points its API calls)
    engine_port: int = 5000
    engine_host: str = "0.0.0.0"

    # ── SSE Streaming ──────────────────────────────────────
    # Enable SSE streaming for /v1/chat/completions
    sse_enabled: bool = True
    # Maximum time (seconds) to keep an SSE connection open
    sse_max_duration_s: float = 300.0
    # Delay between SSE chunks (seconds) — 0 for immediate
    sse_chunk_delay_s: float = 0.0

    # ── Visual Bypass ──────────────────────────────────────
    # When True, UI/Design requests skip Z3/AC-3 solver verification
    # IMPORTANT: Set ZENIC_NO_VISUAL_BYPASS=1 in .env when using Cline,
    # because Cline messages often contain UI keywords ("page", "form",
    # "button", "style", "screen") that trigger false visual bypass,
    # causing the AI model to be skipped and returning empty/incomplete responses.
    visual_bypass_enabled: bool = True
    # Criticality level assigned to visual/UI requests (1=FAST, skips solver)
    visual_criticality_level: int = 1
    # Keywords that trigger visual bypass
    visual_keywords: List[str] = field(default_factory=lambda: [
        "ui", "design", "interface", "frontend", "component",
        "layout", "css", "html", "react", "vue", "angular",
        "tailwind", "bootstrap", "material", "figma",
        "artifact", "render", "widget", "page", "form",
        "button", "card", "modal", "sidebar", "navbar",
        "dashboard", "panel", "dialog", "menu", "toolbar",
        "visual", "style", "theme", "animation", "responsive",
        "mobile", "tablet", "desktop", "screen", "viewport",
    ])

    # ── Design System Preservation ─────────────────────────
    # When True, ContextAgent does NOT truncate Design System prompts
    preserve_design_systems: bool = True
    # Token budget multiplier for requests containing design systems
    design_system_budget_multiplier: float = 2.5
    # Signatures that indicate a Design System prompt from Open Design
    design_system_signatures: List[str] = field(default_factory=lambda: [
        "design-system",
        "design_system",
        "DesignSystem",
        "stripe-design",
        "material-design",
        "ant-design",
        "chakra",
        "tailwind-config",
        "theme-config",
        "token-system",
        "color-palette",
        "typography-scale",
        "spacing-system",
    ])

    # ── Artifact Wrapping ──────────────────────────────────
    # When True, code output is wrapped in <artifact> tags
    artifact_wrapping_enabled: bool = True
    # Default artifact type for Open Design
    default_artifact_type: str = "application/vnd.ant.code"
    # Supported artifact types
    artifact_types: Dict[str, str] = field(default_factory=lambda: {
        "html": "text/html",
        "react": "application/vnd.ant.code",
        "css": "text/css",
        "javascript": "application/javascript",
        "python": "text/x-python",
        "json": "application/json",
        "svg": "image/svg+xml",
    })

    # ── Fractal SSE Packaging ──────────────────────────────
    # When True, FractalGenerator phases are streamed as SSE events
    fractal_sse_enabled: bool = True
    # Event types for each fractal phase
    fractal_phase_events: Dict[str, str] = field(default_factory=lambda: {
        "structure": "fractal_structure",
        "skeletons": "fractal_skeleton",
        "fill": "fractal_fill",
    })

    def to_dict(self) -> Dict[str, Any]:
        """Serialize config to dictionary."""
        return {
            "open_design_origins": self.open_design_origins,
            "engine_port": self.engine_port,
            "engine_host": self.engine_host,
            "sse_enabled": self.sse_enabled,
            "sse_max_duration_s": self.sse_max_duration_s,
            "visual_bypass_enabled": self.visual_bypass_enabled,
            "visual_criticality_level": self.visual_criticality_level,
            "preserve_design_systems": self.preserve_design_systems,
            "design_system_budget_multiplier": self.design_system_budget_multiplier,
            "artifact_wrapping_enabled": self.artifact_wrapping_enabled,
            "fractal_sse_enabled": self.fractal_sse_enabled,
        }

    @classmethod
    def from_env(cls) -> "OpenDesignConfig":
        """Create config from environment variables.

        Environment variables:
            OPEN_DESIGN_ORIGINS: comma-separated list of allowed origins
            OPEN_DESIGN_ENGINE_PORT: ZENIC-AGENTS port (default: 5000)
            OPEN_DESIGN_SSE_ENABLED: 'true'/'false' (default: true)
            OPEN_DESIGN_VISUAL_BYPASS: 'true'/'false' (default: true)
            OPEN_DESIGN_PRESERVE_DS: 'true'/'false' (default: true)
            OPEN_DESIGN_ARTIFACT_WRAP: 'true'/'false' (default: true)
            OPEN_DESIGN_FRACTAL_SSE: 'true'/'false' (default: true)
        """
        config = cls()

        # Origins
        origins_env = os.getenv("OPEN_DESIGN_ORIGINS", "")
        if origins_env:
            config.open_design_origins = [
                o.strip() for o in origins_env.split(",") if o.strip()
            ]

        # Engine port
        port_env = os.getenv("OPEN_DESIGN_ENGINE_PORT", "")
        if port_env:
            try:
                config.engine_port = int(port_env)
            except ValueError:
                pass

        # SSE enabled
        sse_env = os.getenv("OPEN_DESIGN_SSE_ENABLED", "true").lower()
        config.sse_enabled = sse_env in ("true", "1", "yes")

        # Visual bypass
        vb_env = os.getenv("OPEN_DESIGN_VISUAL_BYPASS", "true").lower()
        config.visual_bypass_enabled = vb_env in ("true", "1", "yes")

        # ZENIC_NO_VISUAL_BYPASS: Override to disable visual bypass for Cline
        # This takes priority over OPEN_DESIGN_VISUAL_BYPASS
        if os.getenv("ZENIC_NO_VISUAL_BYPASS", "0") == "1":
            config.visual_bypass_enabled = False

        # Preserve Design Systems
        ds_env = os.getenv("OPEN_DESIGN_PRESERVE_DS", "true").lower()
        config.preserve_design_systems = ds_env in ("true", "1", "yes")

        # Artifact wrapping
        aw_env = os.getenv("OPEN_DESIGN_ARTIFACT_WRAP", "true").lower()
        config.artifact_wrapping_enabled = aw_env in ("true", "1", "yes")

        # Fractal SSE
        fs_env = os.getenv("OPEN_DESIGN_FRACTAL_SSE", "true").lower()
        config.fractal_sse_enabled = fs_env in ("true", "1", "yes")

        # Budget multiplier
        bm_env = os.getenv("OPEN_DESIGN_DS_BUDGET_MULTIPLIER", "")
        if bm_env:
            try:
                config.design_system_budget_multiplier = float(bm_env)
            except ValueError:
                pass

        return config


# ── Singleton ──────────────────────────────────────────────
_config: Optional[OpenDesignConfig] = None


def get_open_design_config() -> OpenDesignConfig:
    """Get or create the singleton OpenDesignConfig."""
    global _config
    if _config is None:
        _config = OpenDesignConfig.from_env()
        logger.info(
            "OpenDesign: config loaded (SSE=%s, visual_bypass=%s, "
            "preserve_ds=%s, artifact_wrap=%s, fractal_sse=%s)",
            _config.sse_enabled, _config.visual_bypass_enabled,
            _config.preserve_design_systems, _config.artifact_wrapping_enabled,
            _config.fractal_sse_enabled,
        )
    return _config


def reload_open_design_config() -> OpenDesignConfig:
    """Force reload config from environment (useful for testing)."""
    global _config
    _config = None
    return get_open_design_config()
