"""ModelManager singleton — uses shared Singleton class."""

from src.core.shared.singleton import Singleton

_model_manager = Singleton(
    lambda: __import__("src.core.model_mgr_parts.manager", fromlist=["ModelManager"]).ModelManager(),
    name="ModelManager",
)


def get_model_manager():
    """Get or create the ModelManager singleton."""
    return _model_manager.get()


def init_model_manager(lazy_load=True, idle_timeout_s=None, ram_budget_mb=None):
    """Initialize ModelManager with custom parameters (thread-safe).

    Raises:
        RuntimeError: If ModelManager is already initialized.
    """
    def factory():
        from .manager import ModelManager
        return ModelManager(
            lazy_load=lazy_load,
            idle_timeout_s=idle_timeout_s,
            ram_budget_mb=ram_budget_mb,
        )

    instance = _model_manager.init(factory)
    instance.start_auto_unload_monitor()
    return instance


def reset_model_manager():
    """Reset the ModelManager singleton (for testing)."""
    _model_manager.reset()
