"""
ProjectGenMixin — Project generation methods for AutomationEngine.

Contains:
  - Automation project generation (TemplateEngine v2 + legacy)
  - Individual file generators (main.py, workflows.py, config.py, README.md)
"""

import os
import logging
from typing import Dict, Any, List

from . import types as _types
from .types import (
    ActionType,
    Workflow,
)
from .crud import CoreCRUDMixin  # noqa: F401 — needed for _extract_name / _save_workflow

logger = logging.getLogger(__name__)


class ProjectGenMixin:
    """Project generation methods for AutomationEngine."""

    # ================================================================
    #  WORKFLOW GENERATION (from natural language)
    # ================================================================

    def generate_automation_project(self, description: str, output_dir: str = "") -> Dict[str, Any]:
        """
        Genera un proyecto de automatización completo.
        Usa TemplateEngine si disponible, sino usa legacy f-strings.
        """
        if self._template_engine:
            return self._generate_automation_v2(description, output_dir)
        return self._generate_automation_legacy(description, output_dir)

    def _generate_automation_v2(self, description: str, output_dir: str = "") -> Dict[str, Any]:
        """
        Genera automatización con TemplateEngine + bloques de acción reales.
        """
        if not output_dir:
            output_dir = os.path.join(_types.PROJECTS_DIR, self._extract_name(description))
        os.makedirs(output_dir, exist_ok=True)

        workflow = self.create_from_description(description)

        # Suggest blocks for automation
        suggested_blocks = self._template_engine.suggest_blocks(description)

        from src.core.template_engine import CompositionPlan
        composition = CompositionPlan(
            base_template="automations/base",
            app_template="",
            blocks=suggested_blocks,
            variables={
                "project_name": workflow.name,
                "app_name": workflow.name,
                "template_type": "automation",
                "db_name": "automation.db",
                "port": 8001,
                "secret_key": "change-this",
                "debug": True,
                "version": "1.0.0",
            },
            entities=[{
                "name": workflow.name,
                "fields": [],
                "trigger_config": workflow.trigger.config,
                "actions": [{"type": a.type.value, "config": a.config} for a in workflow.actions],
            }],
        )

        try:
            files = self._template_engine.render_automation(composition)

            for filepath, content in files.items():
                full_path = os.path.join(output_dir, filepath)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "w", encoding="utf-8") as f:
                    f.write(content)

            return {
                "workflow": workflow,
                "path": output_dir,
                "files": list(files.keys()),
                "blocks_used": suggested_blocks,
                "status": "generated",
            }
        except Exception as e:
            logger.error(f"AutomationEngine v2: Failed: {e}")
            # Fall back to legacy
            return self._generate_automation_legacy(description, output_dir)

    def _generate_automation_legacy(self, description: str, output_dir: str = "") -> Dict[str, Any]:
        """
        Genera un proyecto de automatización completo a partir de una descripción.

        Crea un proyecto Python independiente con:
          - main.py (scheduler + workflow engine)
          - workflows.py (definiciones de workflows)
          - config.py (configuración)
          - requirements.txt
        """
        if not output_dir:
            output_dir = os.path.join(_types.PROJECTS_DIR, self._extract_name(description))
        os.makedirs(output_dir, exist_ok=True)

        workflow = self.create_from_description(description)

        files = {
            "main.py": self._gen_automation_main(workflow, description),
            "workflows.py": self._gen_automation_workflows(workflow),
            "config.py": self._gen_automation_config(workflow, description),
            "requirements.txt": "apscheduler>=3.10.0\naiosmtplib>=3.0.0\n",
            "README.md": self._gen_automation_readme(workflow, description),
        }

        for filepath, content in files.items():
            full_path = os.path.join(output_dir, filepath)
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)

        return {
            "workflow": workflow,
            "path": output_dir,
            "files": list(files.keys()),
            "status": "generated",
        }

    def _gen_automation_main(self, wf: Workflow, description: str) -> str:
        """Genera main.py para proyecto de automatización."""
        schedule_config = wf.trigger.config
        interval = schedule_config.get("interval", "daily")
        hour = schedule_config.get("hour", 9)
        minute = schedule_config.get("minute", 0)

        # Build trigger config for APScheduler
        if interval == "hourly":
            trigger_code = "IntervalTrigger(hours=1)"
        elif interval == "daily":
            trigger_code = f"CronTrigger(hour={hour}, minute={minute})"
        elif interval == "weekly":
            day = schedule_config.get("day_of_week", "mon")
            trigger_code = f"CronTrigger(day_of_week='{day}', hour={hour}, minute={minute})"
        elif interval == "monthly":
            day = schedule_config.get("day", 1)
            trigger_code = f"CronTrigger(day={day}, hour={hour}, minute={minute})"
        else:
            trigger_code = f"CronTrigger(hour={hour}, minute={minute})"

        actions_code = []
        for i, action in enumerate(wf.actions):
            if action.type == ActionType.SEND_EMAIL:
                actions_code.append(f'''
    # Action {i+1}: Send Email
    print(f"Sending email to {action.config.get('to', 'admin@company.com')}...")
    # from services import EmailService
    # EmailService.send(to="{action.config.get('to', 'admin@company.com')}", subject="{action.config.get('subject', 'Report')}")
''')
            elif action.type == ActionType.SEND_NOTIFICATION:
                actions_code.append(f'''
    # Action {i+1}: Send Notification
    print(f"Notification: {action.config.get('message', 'Workflow executed')}")
''')
            elif action.type == ActionType.GENERATE_REPORT:
                actions_code.append(f'''
    # Action {i+1}: Generate Report
    print("Generating report...")
    # from services import ReportService
    # report = ReportService.generate(template="{action.config.get('template', 'default')}")
''')
            elif action.type == ActionType.DATABASE_OPERATION:
                actions_code.append(f'''
    # Action {i+1}: Database Operation
    print("Executing database operation...")
    # from services import DatabaseService
    # DatabaseService.{action.config.get('operation', 'backup')}()
''')
            else:
                actions_code.append(f'''
    # Action {i+1}: {action.type.value}
    print("Executing {action.type.value}...")
''')

        actions_str = "\n".join(actions_code) if actions_code else '    print("No actions defined")'

        return f'''"""
{wf.name} - Automation
Auto-generated by ZENIC-AGENTS

Description: {description}
Schedule: {interval} at {hour}:{minute:02d}
"""
import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(levelname)s: %(message)s')
logger = logging.getLogger("{wf.name}")


async def run_workflow():
    """Ejecuta el workflow de automatización."""
    logger.info(f"Running workflow: {wf.name}")
    start = datetime.now()
{actions_str}
    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"Workflow completed in {elapsed:.2f}s")


async def main():
    """Punto de entrada principal."""
    scheduler = AsyncIOScheduler()

    # Schedule the workflow
    scheduler.add_job(
        run_workflow,
        {trigger_code},
        id="{wf.name}",
        name="{wf.name}",
        replace_existing=True,
    )

    logger.info(f"Scheduler started. Workflow '{wf.name}' scheduled ({interval}).")
    logger.info("Press Ctrl+C to exit.")

    scheduler.start()

    # Run once immediately on startup
    await run_workflow()

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    asyncio.run(main())
'''

    def _gen_automation_workflows(self, wf: Workflow) -> str:
        """Genera workflows.py - Definiciones de workflows."""
        return f'''"""
{wf.name} - Workflow Definitions
Auto-generated by ZENIC-AGENTS
"""
from dataclasses import dataclass, field
from typing import Dict, Any, List
from enum import Enum


class TriggerType(str, Enum):
    SCHEDULE = "schedule"
    EVENT = "event"
    WEBHOOK = "webhook"


class ActionType(str, Enum):
    SEND_EMAIL = "send_email"
    SEND_NOTIFICATION = "send_notification"
    RUN_SCRIPT = "run_script"
    DATABASE_OPERATION = "database_operation"
    GENERATE_REPORT = "generate_report"
    HTTP_REQUEST = "http_request"


@dataclass
class Action:
    type: ActionType = ActionType.SEND_NOTIFICATION
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowDefinition:
    name: str = ""
    description: str = ""
    trigger_type: TriggerType = TriggerType.SCHEDULE
    trigger_config: Dict[str, Any] = field(default_factory=dict)
    actions: List[Action] = field(default_factory=list)


# ============================================================
#  WORKFLOW DEFINITIONS
# ============================================================

WORKFLOWS = [
    WorkflowDefinition(
        name="{wf.name}",
        description="{wf.description}",
        trigger_type=TriggerType.{wf.trigger.type.name},
        trigger_config={wf.trigger.config},
        actions=[
{chr(10).join(f"            Action(ActionType.{a.type.name}, {a.config})," for a in wf.actions)}
        ],
    ),
]


def get_workflow(name: str) -> WorkflowDefinition:
    """Obtiene un workflow por nombre."""
    for wf in WORKFLOWS:
        if wf.name == name:
            return wf
    return WORKFLOWS[0] if WORKFLOWS else None
'''

    def _gen_automation_config(self, wf: Workflow, description: str) -> str:
        """Genera config.py para proyecto de automatización."""
        return f'''"""
{wf.name} - Configuration
Auto-generated by ZENIC-AGENTS
"""
import os


class Config:
    APP_NAME = "{wf.name}"
    DEBUG = True
    LOG_LEVEL = "INFO"

    # Email SMTP Configuration
    SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")

    # Notification Settings
    NOTIFICATION_EMAIL = os.environ.get("NOTIFICATION_EMAIL", "admin@company.com")
    NOTIFICATION_CHANNEL = os.environ.get("NOTIFICATION_CHANNEL", "log")

    # Database
    DB_PATH = os.path.join(os.path.dirname(__file__), "data", "automation.db")

    # Scheduler
    SCHEDULER_TIMEZONE = "UTC"
    SCHEDULER_JOBSTORES = "default"
    SCHEDULER_MAX_INSTANCES = 1
'''

    def _gen_automation_readme(self, wf: Workflow, description: str) -> str:
        """Genera README.md para proyecto de automatización."""
        return f'''# {wf.name}

> Automation generated by **ZENIC-AGENTS**

## Description

{description}

## Schedule

- **Type**: {wf.trigger.type.value}
- **Config**: {wf.trigger.config}

## Actions

{chr(10).join(f"- {a.type.value}: {a.config}" for a in wf.actions)}

## Quick Start

```bash
pip install -r requirements.txt
python main.py
```

## Configuration

Edit `config.py` with your SMTP credentials and settings.

## Environment Variables

- `SMTP_HOST` - SMTP server host
- `SMTP_PORT` - SMTP server port
- `SMTP_USER` - SMTP username
- `SMTP_PASSWORD` - SMTP password
- `NOTIFICATION_EMAIL` - Email for notifications
'''
