"""
ProjectRunner — Auto-run generated projects with virtualenv + dependency installation.

Problem: Generated projects are written to disk but never validated by
actually running them. Users don't know if the code works until they
manually install deps and start the server.

Solution: ProjectRunner automates:
  1. Create virtualenv in project directory
  2. Install dependencies from requirements.txt
  3. Initialize database (create tables)
  4. Start the server on a free port
  5. Health check to verify it's running
  6. Return process info for management

M6 Implementation: Runs on Termux/Android with python3 -m venv support.
"""

import logging
import os
from typing import Optional

from ._types import RunResult
from ._helpers_mixin import HelpersMixin
from ._api_mixin import PublicAPIMixin

logger = logging.getLogger(__name__)

__all__ = ["ProjectRunner", "RunResult"]


class ProjectRunner(PublicAPIMixin, HelpersMixin):
    """Run generated projects automatically with venv + deps + server start."""

    def __init__(self, projects_dir: Optional[str] = None):
        """
        Args:
            projects_dir: Base directory for generated projects.
                         Defaults to ~/.zenic_agents/projects/
        """
        if projects_dir:
            self._projects_dir = projects_dir
        else:
            from src.core.shared.db_initializer import get_projects_dir
            self._projects_dir = str(get_projects_dir())
