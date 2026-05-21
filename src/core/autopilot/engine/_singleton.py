"""AutopilotEngine singleton — uses shared Singleton class."""

from src.core.shared.singleton import Singleton

_autopilot_engine = Singleton(
    lambda: __import__("src.core.autopilot.engine.core", fromlist=["AutopilotEngine"]).AutopilotEngine(),
    name="AutopilotEngine",
)


def get_autopilot_engine(db_path="autopilot_engine.sqlite"):
    """Get or create the AutopilotEngine singleton."""
    return _autopilot_engine.get()


def reset_autopilot_engine():
    """Reset the AutopilotEngine singleton (for testing)."""
    _autopilot_engine.reset()
