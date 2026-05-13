"""
ZENIC-AGENTS - FileExecutor (Phase 7.1)

Ejecutor de operaciones reales en el filesystem con protección path-traversal.
"""

import asyncio
import logging
import os
import shutil
from typing import Any, Dict

from .base import ActionExecutor, ActionResult, _safe_path

logger = logging.getLogger(__name__)


class FileExecutor(ActionExecutor):
    """Ejecutor de operaciones reales en el filesystem con protección path-traversal.

    Config: {operation, source, destination, content, pattern, base_dir}
    Operations: read, write, append, copy, move, delete, list, mkdir, exists
    """

    async def execute(self, config: Dict[str, Any], context: Dict[str, Any]) -> ActionResult:
        start = self._measure()
        operation = config.get("operation", "read").lower()
        base_dir = config.get("base_dir", os.getcwd())
        source = config.get("source", "")
        destination = config.get("destination", "")
        content = config.get("content", "")
        pattern = config.get("pattern", "*")

        valid_ops = {"read", "write", "append", "copy", "move", "delete", "list", "mkdir", "exists"}
        if operation not in valid_ops:
            return ActionResult(False, {"operation": operation},
                                f"Invalid file operation: {operation}. Must be one of {valid_ops}", self._elapsed_ms(start))
        try:
            if source: source = _safe_path(source, base_dir)
            if destination: destination = _safe_path(destination, base_dir)

            ops = {"read": lambda: self._read(source), "write": lambda: self._write(destination or source, content),
                   "append": lambda: self._append(destination or source, content), "copy": lambda: self._copy(source, destination),
                   "move": lambda: self._move(source, destination), "delete": lambda: self._delete(source),
                   "list": lambda: self._list(source or base_dir, pattern), "mkdir": lambda: self._mkdir(source),
                   "exists": lambda: self._exists(source)}
            result_data = await ops[operation]()
            elapsed = self._elapsed_ms(start)
            logger.info(f"FileExecutor: {operation} completed - {source or base_dir}")
            return ActionResult(True, result_data, duration_ms=elapsed)
        except ValueError as e:
            return ActionResult(False, {"operation": operation}, str(e), self._elapsed_ms(start))
        except Exception as e:
            elapsed = self._elapsed_ms(start)
            logger.error(f"FileExecutor: {operation} failed: {e}")
            return ActionResult(False, {"operation": operation, "source": source}, str(e), elapsed)

    async def _read(self, path):
        if not os.path.exists(path): raise FileNotFoundError(f"File not found: {path}")
        def _do_read():
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                return f.read()
        content = await asyncio.to_thread(_do_read)
        return {"content": content, "size": len(content), "path": path}

    async def _write(self, path, content):
        d = os.path.dirname(path)
        if d: os.makedirs(d, exist_ok=True)
        def _do_write():
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        await asyncio.to_thread(_do_write)
        return {"path": path, "size": len(content), "operation": "write"}

    async def _append(self, path, content):
        def _do_append():
            with open(path, "a", encoding="utf-8") as f:
                f.write(content)
        await asyncio.to_thread(_do_append)
        return {"path": path, "appended_size": len(content), "operation": "append"}

    async def _copy(self, source, destination):
        if not os.path.exists(source): raise FileNotFoundError(f"Source not found: {source}")
        d = os.path.dirname(destination)
        if d: os.makedirs(d, exist_ok=True)
        def _do(): shutil.copytree(source, destination, dirs_exist_ok=True) if os.path.isdir(source) else shutil.copy2(source, destination)
        await asyncio.to_thread(_do)
        return {"source": source, "destination": destination, "operation": "copy"}

    async def _move(self, source, destination):
        if not os.path.exists(source): raise FileNotFoundError(f"Source not found: {source}")
        d = os.path.dirname(destination)
        if d: os.makedirs(d, exist_ok=True)
        await asyncio.to_thread(lambda: shutil.move(source, destination))
        return {"source": source, "destination": destination, "operation": "move"}

    async def _delete(self, path):
        if not os.path.exists(path): raise FileNotFoundError(f"Path not found: {path}")
        def _do(): shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
        await asyncio.to_thread(_do)
        return {"path": path, "operation": "delete"}

    async def _list(self, path, pattern):
        if not os.path.isdir(path): raise NotADirectoryError(f"Not a directory: {path}")
        import glob as glob_module
        files = await asyncio.to_thread(lambda: glob_module.glob(os.path.join(path, pattern)))
        return {"files": files, "count": len(files), "path": path, "pattern": pattern}

    async def _mkdir(self, path):
        await asyncio.to_thread(lambda: os.makedirs(path, exist_ok=True))
        return {"path": path, "operation": "mkdir"}

    async def _exists(self, path):
        exists = await asyncio.to_thread(os.path.exists, path)
        is_dir = await asyncio.to_thread(os.path.isdir, path) if exists else False
        is_file = await asyncio.to_thread(os.path.isfile, path) if exists else False
        return {"path": path, "exists": exists, "is_dir": is_dir, "is_file": is_file}
