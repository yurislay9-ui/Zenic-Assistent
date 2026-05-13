"""Shared fixtures for automation engine tests."""

import os
import sqlite3
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.core.automation_engine import (
    AutomationEngine,
    Workflow,
    WorkflowExecution,
    Trigger,
    Action,
    TriggerType,
    ActionType,
)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Redirect the automation DB to a temp directory."""
    db_dir = str(tmp_path / "db")
    db_path = os.path.join(db_dir, "automation.sqlite")
    projects_dir = str(tmp_path / "projects")
    os.makedirs(db_dir, exist_ok=True)

    monkeypatch.setattr("src.core.automation_parts.types.DB_DIR", db_dir)
    monkeypatch.setattr("src.core.automation_parts.types.DB_PATH", db_path)
    monkeypatch.setattr("src.core.automation_parts.types.PROJECTS_DIR", projects_dir)
    monkeypatch.setattr("src.core.automation_engine.DB_DIR", db_dir)
    monkeypatch.setattr("src.core.automation_engine.DB_PATH", db_path)
    monkeypatch.setattr("src.core.automation_engine.PROJECTS_DIR", projects_dir)

    return db_path


@pytest.fixture
def engine(temp_db):
    """Create an AutomationEngine with a temp DB."""
    with patch("src.core.automation_engine.AutomationEngine._init_db") as mock_init, \
         patch("src.core.automation_engine.AutomationEngine._load_workflows") as mock_load:
        eng = AutomationEngine(
            thinking_engine=None,
            template_engine=None,
            executor_registry=None,
        )

    # Actually init the DB now with the temp path
    eng._init_db()
    eng._workflows = {}
    return eng


@pytest.fixture
def sample_workflow(engine):
    """Create a sample workflow via the engine."""
    return engine.create_workflow(
        name="Daily Sales Report",
        description="Send daily sales report by email",
        trigger=Trigger(
            type=TriggerType.SCHEDULE,
            config={"interval": "daily", "hour": 9, "minute": 0},
        ),
        actions=[
            Action(type=ActionType.GENERATE_REPORT, config={"template": "sales", "format": "html"}),
            Action(type=ActionType.SEND_EMAIL, config={"to": "admin@co.com", "subject": "Sales"}),
        ],
    )
