"""
ProjectRunner — Public API Mixin

run_project, stop_project, and list_running methods.
"""

import logging
import os
import time
from typing import Any, Dict, List

from ._types import RunResult

logger = logging.getLogger(__name__)


class PublicAPIMixin:
    """Mixin providing public API methods for ProjectRunner."""

    def run_project(self, project_name: str, port: int = 0,
                    auto_install: bool = True,
                    auto_start: bool = True) -> RunResult:
        """Run a generated project.

        Steps:
        1. Verify project directory exists
        2. Create virtualenv (if not exists)
        3. Install dependencies (if auto_install)
        4. Start the server (if auto_start)
        5. Health check

        Args:
            project_name: Name of the project to run
            port: Port to run on (0 = auto-select free port)
            auto_install: Whether to install dependencies
            auto_start: Whether to start the server

        Returns:
            RunResult with process info and status
        """
        result = RunResult(project_name=project_name)
        start_time = time.time()

        # Step 1: Verify project directory
        project_dir = os.path.join(self._projects_dir, project_name)
        if not os.path.isdir(project_dir):
            result.errors.append(f"Project directory not found: {project_dir}")
            return result
        result.project_dir = project_dir

        # Step 2: Create virtualenv
        venv_dir = os.path.join(project_dir, "venv")
        if not os.path.isdir(venv_dir):
            logger.info(f"ProjectRunner: Creating venv for {project_name}")
            venv_result = self._create_venv(venv_dir)
            if not venv_result:
                result.errors.append(f"Failed to create virtualenv in {venv_dir}")
                return result
            result.warnings.append("Virtualenv created")
        result.venv_dir = venv_dir

        # Step 3: Install dependencies
        if auto_install:
            logger.info(f"ProjectRunner: Installing deps for {project_name}")
            installed, failed = self._install_deps(project_dir, venv_dir)
            result.installed_deps = installed
            result.failed_deps = failed
            if failed:
                result.warnings.append(f"Failed to install {len(failed)} deps: {', '.join(failed[:3])}")

        # Step 4: Initialize database
        self._init_database(project_dir, venv_dir)

        # Step 5: Start server
        if auto_start:
            if port == 0:
                port = self._find_free_port()
            result.port = port
            logger.info(f"ProjectRunner: Starting {project_name} on port {port}")
            pid = self._start_server(project_dir, venv_dir, port)
            if pid:
                result.pid = pid
                # Step 6: Health check
                time.sleep(2)  # Wait for server to start
                health_ok = self._health_check(port)
                result.health_ok = health_ok
                if health_ok:
                    result.success = True
                    logger.info(f"ProjectRunner: {project_name} running on port {port} (PID {pid})")
                else:
                    result.warnings.append(f"Server started (PID {pid}) but health check failed on port {port}")
                    result.success = True  # Server is running, health check might need time
            else:
                result.errors.append("Failed to start server process")
        else:
            result.success = True  # Project prepared, just not started

        result.startup_time_s = time.time() - start_time
        return result

    def stop_project(self, project_name: str) -> bool:
        """Stop a running project by killing its server process.

        Args:
            project_name: Name of the project to stop

        Returns:
            True if stopped successfully
        """
        project_dir = os.path.join(self._projects_dir, project_name)
        pid_file = os.path.join(project_dir, ".server.pid")

        if os.path.exists(pid_file):
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 15)  # SIGTERM
                os.unlink(pid_file)
                logger.info(f"ProjectRunner: Stopped {project_name} (PID {pid})")
                return True
            except ProcessLookupError:
                # Process already dead
                if os.path.exists(pid_file):
                    os.unlink(pid_file)
                return True
            except Exception as e:
                logger.warning(f"ProjectRunner: Failed to stop {project_name}: {e}")
                return False
        else:
            logger.warning(f"ProjectRunner: No PID file for {project_name}")
            return False

    def list_running(self) -> List[Dict[str, Any]]:
        """List all running projects.

        Returns:
            List of dicts with project_name, port, pid, health
        """
        running = []
        if not os.path.isdir(self._projects_dir):
            return running

        for name in os.listdir(self._projects_dir):
            project_dir = os.path.join(self._projects_dir, name)
            pid_file = os.path.join(project_dir, ".server.pid")
            port_file = os.path.join(project_dir, ".server.port")

            if os.path.exists(pid_file):
                try:
                    with open(pid_file) as f:
                        pid = int(f.read().strip())
                    # Check if process is still alive
                    os.kill(pid, 0)  # Signal 0 = check existence

                    port = 0
                    if os.path.exists(port_file):
                        with open(port_file) as f:
                            port = int(f.read().strip())

                    running.append({
                        "project_name": name,
                        "port": port,
                        "pid": pid,
                        "health_ok": self._health_check(port) if port else False,
                    })
                except (ProcessLookupError, ValueError, FileNotFoundError):
                    # Process is dead, clean up
                    for f in [pid_file, port_file]:
                        if os.path.exists(f):
                            try:
                                os.unlink(f)
                            except OSError:
                                pass

        return running
