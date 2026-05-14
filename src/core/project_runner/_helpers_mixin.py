"""
ProjectRunner — Internal Helper Methods

Virtualenv creation, dependency installation, database initialization,
server startup, health checks, and port discovery.
"""

import logging
import os
import socket
import subprocess
import sys
from typing import List, Optional, Tuple

from ._types import INSTALL_TIMEOUT, HEALTH_TIMEOUT

logger = logging.getLogger(__name__)


class HelpersMixin:
    """Mixin providing internal helper methods for ProjectRunner."""

    def _create_venv(self, venv_dir: str) -> bool:
        """Create a Python virtual environment."""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "venv", venv_dir],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                logger.error(f"venv creation failed: {result.stderr}")
                return False
            return True
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"venv creation error: {e}")
            return False

    def _install_deps(self, project_dir: str, venv_dir: str) -> Tuple[List[str], List[str]]:
        """Install dependencies from requirements.txt.

        Returns:
            Tuple of (installed_list, failed_list)
        """
        req_file = os.path.join(project_dir, "requirements.txt")
        if not os.path.exists(req_file):
            return [], ["requirements.txt not found"]

        # Read requirements
        with open(req_file) as f:
            requirements = [line.strip() for line in f
                          if line.strip() and not line.startswith("#")]

        if not requirements:
            return [], []

        # Determine pip path
        if os.name == "nt":
            pip_path = os.path.join(venv_dir, "Scripts", "pip")
        else:
            pip_path = os.path.join(venv_dir, "bin", "pip")

        if not os.path.exists(pip_path):
            # Try pip3
            pip_path = pip_path + "3"
        if not os.path.exists(pip_path):
            # Use the venv python -m pip
            if os.name == "nt":
                python_path = os.path.join(venv_dir, "Scripts", "python")
            else:
                python_path = os.path.join(venv_dir, "bin", "python")
            pip_path = python_path
            use_module = True
        else:
            use_module = False

        installed = []
        failed = []

        for req in requirements:
            try:
                if use_module:
                    cmd = [pip_path, "-m", "pip", "install", "-q", req]
                else:
                    cmd = [pip_path, "install", "-q", req]

                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=INSTALL_TIMEOUT,
                )
                if result.returncode == 0:
                    installed.append(req)
                else:
                    failed.append(req)
                    logger.debug(f"Failed to install {req}: {result.stderr[:100]}")
            except subprocess.TimeoutExpired:
                failed.append(req)
                logger.warning(f"Timeout installing {req}")
            except Exception as e:
                failed.append(req)
                logger.warning(f"Error installing {req}: {e}")

        return installed, failed

    def _init_database(self, project_dir: str, venv_dir: str) -> bool:
        """Initialize the SQLite database for the project."""
        # Check if there's a database.py or init_db script
        db_file = os.path.join(project_dir, "database.py")
        if not os.path.exists(db_file):
            return True  # No database module, skip

        # Try to import and run init
        if os.name == "nt":
            python_path = os.path.join(venv_dir, "Scripts", "python")
        else:
            python_path = os.path.join(venv_dir, "bin", "python")

        if not os.path.exists(python_path):
            python_path = sys.executable

        try:
            result = subprocess.run(
                [python_path, "-c",
                 "import sys; sys.path.insert(0, '.'); "
                 "from database import init_db; init_db()"],
                capture_output=True, text=True, timeout=15,
                cwd=project_dir,
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"Database init skipped: {e}")
            return False

    def _start_server(self, project_dir: str, venv_dir: str,
                       port: int) -> Optional[int]:
        """Start the project server as a background process."""
        # Determine python path
        if os.name == "nt":
            python_path = os.path.join(venv_dir, "Scripts", "python")
        else:
            python_path = os.path.join(venv_dir, "bin", "python")

        if not os.path.exists(python_path):
            python_path = sys.executable

        # Check for main.py or app.py
        main_file = None
        for name in ["main.py", "app.py", "server.py"]:
            if os.path.exists(os.path.join(project_dir, name)):
                main_file = name
                break

        if not main_file:
            logger.warning(f"No main.py/app.py found in {project_dir}")
            return None

        # Start server
        env = os.environ.copy()
        env["PORT"] = str(port)

        try:
            process = subprocess.Popen(
                [python_path, main_file],
                cwd=project_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                # Detach from parent process group
                start_new_session=True,
            )

            pid = process.pid

            # Save PID and port for management
            pid_file = os.path.join(project_dir, ".server.pid")
            port_file = os.path.join(project_dir, ".server.port")
            with open(pid_file, "w") as f:
                f.write(str(pid))
            with open(port_file, "w") as f:
                f.write(str(port))

            return pid

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return None

    def _health_check(self, port: int) -> bool:
        """Check if the server is responding on the given port."""
        try:
            import urllib.request
            url = f"http://localhost:{port}/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as resp:
                return resp.status == 200
        except Exception:
            # Try / root as fallback
            try:
                import urllib.request
                url = f"http://localhost:{port}/"
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=HEALTH_TIMEOUT) as resp:
                    return resp.status in (200, 404)  # 404 means server is running
            except Exception:
                return False

    @staticmethod
    def _find_free_port() -> int:
        """Find a free TCP port."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('', 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]
