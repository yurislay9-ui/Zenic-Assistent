"""
Distributed Tracing — Configuration and Initialization.

Contains TracingConfig, global state management, init_tracing(),
and the _setup_exporter() helper.
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from src.core.shared._version import ZENIC_VERSION

logger = logging.getLogger(__name__)

# ── Global state ──────────────────────────────────────────
_tracer: Optional[Any] = None
_tracing_enabled: bool = False
_provider: Optional[Any] = None


@dataclass
class TracingConfig:
    """Configuration for distributed tracing.

    Attributes:
        enabled: Whether tracing is active.
        exporter: Export destination ('jaeger', 'otlp', 'console', 'none').
        endpoint: Exporter endpoint URL (e.g. 'http://jaeger:4317').
        service_name: Service name for trace attribution.
        sample_rate: Trace sample rate (0.0 to 1.0).
        max_span_attributes: Maximum attributes per span.
    """
    enabled: bool = False
    exporter: str = "console"
    endpoint: str = ""
    service_name: str = "zenic-agents"
    sample_rate: float = 1.0
    max_span_attributes: int = 128

    @classmethod
    def from_env(cls) -> "TracingConfig":
        """Create config from environment variables."""
        return cls(
            enabled=os.getenv("ZENIC_TRACING_ENABLED", "false").lower() == "true",
            exporter=os.getenv("ZENIC_TRACING_EXPORTER", "console"),
            endpoint=os.getenv("ZENIC_TRACING_ENDPOINT", ""),
            service_name=os.getenv("ZENIC_SERVICE_NAME", "zenic-agents"),
            sample_rate=float(os.getenv("ZENIC_TRACING_SAMPLE_RATE", "1.0")),
        )


def init_tracing(config: Optional[TracingConfig] = None) -> bool:
    """Initialize the distributed tracing subsystem.

    Attempts to set up OpenTelemetry SDK. Falls back to
    correlation-ID-only mode if OTel dependencies are missing.

    Args:
        config: Tracing configuration. If None, reads from env.

    Returns:
        True if full OTel tracing was initialized,
        False if using correlation-ID fallback.
    """
    global _tracer, _tracing_enabled, _provider

    if config is None:
        config = TracingConfig.from_env()

    if not config.enabled:
        _tracing_enabled = False
        logger.info("Tracing: DISABLED (set ZENIC_TRACING_ENABLED=true to enable)")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({
            "service.name": config.service_name,
            "service.version": ZENIC_VERSION,
        })

        sampler = TraceIdRatioBased(rate=config.sample_rate)
        provider = TracerProvider(
            resource=resource,
            sampler=sampler,
        )

        _setup_exporter(provider, config)

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(config.service_name, ZENIC_VERSION)
        _provider = provider
        _tracing_enabled = True

        logger.info(
            "Tracing: ENABLED (exporter=%s, sample_rate=%.2f, service=%s)",
            config.exporter, config.sample_rate, config.service_name,
        )
        return True

    except ImportError:
        logger.info(
            "Tracing: OpenTelemetry not installed — using correlation-ID fallback"
        )
        _tracing_enabled = False
        return False
    except Exception as exc:
        logger.warning("Tracing: Initialization failed (%s) — using fallback", exc)
        _tracing_enabled = False
        return False


def _setup_exporter(provider: Any, config: TracingConfig) -> None:
    """Configure the trace exporter on the provider."""
    if config.exporter == "none":
        return

    if config.exporter == "console":
        try:
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        except ImportError:
            pass
        return

    if config.exporter in ("jaeger", "otlp"):
        try:
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            if config.exporter == "otlp":
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-unresolved]
                    OTLPSpanExporter,
                )
                endpoint = config.endpoint or "http://localhost:4317"
                exporter = OTLPSpanExporter(endpoint=endpoint)
            else:
                try:
                    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (  # type: ignore[import-unresolved]
                        OTLPSpanExporter,
                    )
                    endpoint = config.endpoint or "http://localhost:4317"
                    exporter = OTLPSpanExporter(endpoint=endpoint)
                except ImportError:
                    from opentelemetry.exporter.jaeger.thrift import (  # type: ignore[import-unresolved]
                        JaegerExporter,
                    )
                    endpoint = config.endpoint or "http://localhost:14268/api/traces"
                    exporter = JaegerExporter(
                        agent_host_name=config.endpoint.split("://")[-1].split(":")[0] if config.endpoint else "localhost",
                        agent_port=6831,
                    )

            provider.add_span_processor(BatchSpanProcessor(exporter))
        except ImportError as exc:
            logger.warning("Tracing: Exporter '%s' not available (%s)", config.exporter, exc)


def get_tracer() -> Optional[Any]:
    """Get the OpenTelemetry tracer (or None if not initialized)."""
    return _tracer
