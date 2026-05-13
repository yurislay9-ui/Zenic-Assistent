"""
ZENIC-AGENTS v1 - Test Configuration

Shared fixtures for all tests (unit, integration, and E2E).
Uses temporary directories to avoid polluting the real data directory.
Also registers the e2e test directory via pytest_collect_modifyitems.
"""

import os
import sys
import tempfile
import shutil
import pytest

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture(autouse=True, scope="session")
def isolate_data_dir():
    """
    Redirect all data directories to a temp dir for the entire test session.
    This ensures tests never touch real user data.
    """
    tmp_dir = tempfile.mkdtemp(prefix="zenic_test_")
    original_env = os.environ.get("ZENIC_DATA_DIR")

    os.environ["ZENIC_DATA_DIR"] = tmp_dir

    # Patch get_data_dir to use tmp_dir
    import src.core.shared.db_initializer as db_init
    original_get_data_dir = db_init.get_data_dir

    def _patched_get_data_dir():
        from pathlib import Path
        p = Path(tmp_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    db_init.get_data_dir = _patched_get_data_dir

    yield tmp_dir

    # Cleanup
    db_init.get_data_dir = original_get_data_dir
    if original_env:
        os.environ["ZENIC_DATA_DIR"] = original_env
    elif "ZENIC_DATA_DIR" in os.environ:
        del os.environ["ZENIC_DATA_DIR"]

    # Close all connections before cleanup
    try:
        db_init.close_all_connections()
    except Exception:
        pass

    shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# E2E test registration
# ---------------------------------------------------------------------------

def pytest_collection_modifyitems(config, items):
    """Automatically mark all tests in the e2e/ directory with @pytest.mark.e2e."""
    e2e_dir = os.path.join(os.path.dirname(__file__), "e2e")
    for item in items:
        # If the test file is inside the e2e directory, add the e2e marker
        if os.path.commonpath([e2e_dir, str(item.fspath)]) == e2e_dir:
            item.add_marker(pytest.mark.e2e)
