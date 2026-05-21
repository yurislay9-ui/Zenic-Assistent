"""ResourceGovernor singleton — uses shared Singleton class."""

from src.core.shared.singleton import Singleton

_resource_governor = Singleton(
    lambda: __import__("src.core.shared.governor_parts.governor", fromlist=["ResourceGovernor"]).ResourceGovernor(),
    name="ResourceGovernor",
)


def get_governor():
    """Get or create the ResourceGovernor singleton."""
    return _resource_governor.get()


def init_governor(ram_limit_mb=None):
    """Initialize ResourceGovernor with custom parameters (thread-safe).

    Raises:
        RuntimeError: If ResourceGovernor is already initialized.
    """
    from .governor import ResourceGovernor

    def factory():
        return ResourceGovernor(ram_limit_mb=ram_limit_mb)

    instance = _resource_governor.init(factory)
    instance.start_monitoring()
    return instance


def reset_governor():
    """Reset the ResourceGovernor singleton (for testing)."""
    _resource_governor.reset()
