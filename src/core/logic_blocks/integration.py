"""
ZENIC-AGENTS - Integration Logic Blocks

Local file operations block.
External integration blocks (email, HTTP, webhook) have been removed
as the system operates as a standalone assistant agent.
"""

import os
import logging
from typing import Any, Dict

from .chain import LogicBlock

logger = logging.getLogger(__name__)


# ============================================================
#  LOCAL INTEGRATION BLOCKS (1)
#  External blocks (EmailSendBlock, HTTPRequestBlock, WebhookCallBlock)
#  removed — system is a standalone assistant, no external connections.
# ============================================================


class FileOperationBlock(LogicBlock):
    """Operaciones de lectura/escritura de archivos locales."""

    name = "file_operation"
    category = "integrations"
    description = "Read/write local file operations"
    inputs = ["path", "operation", "content"]
    outputs = ["content", "path", "status"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            path = data.get("path", data.get("file_path", ""))
            operation = data.get("operation", "read")  # read, write, append, exists, delete
            content = data.get("content", "")
            encoding = data.get("encoding", "utf-8")

            if not path:
                return {"success": False, "error": "No file path provided"}

            # Security: prevent path traversal
            if ".." in path or path.startswith("/"):
                base_dir = context.get("base_dir", context.get("upload_dir", "/tmp"))
                path = os.path.join(base_dir, os.path.basename(path))

            if operation == "read":
                if not os.path.isfile(path):
                    return {"success": False, "error": f"File not found: {path}"}
                with open(path, "r", encoding=encoding) as f:
                    file_content = f.read()
                logger.debug(f"FileOperationBlock: Read {path} ({len(file_content)} bytes)")
                return {
                    "success": True,
                    "content": file_content,
                    "path": path,
                    "size": len(file_content),
                    "status": "read",
                }

            elif operation == "write":
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "w", encoding=encoding) as f:
                    f.write(str(content))
                logger.debug(f"FileOperationBlock: Written {path} ({len(str(content))} bytes)")
                return {
                    "success": True,
                    "path": path,
                    "size": len(str(content)),
                    "status": "written",
                }

            elif operation == "append":
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "a", encoding=encoding) as f:
                    f.write(str(content))
                logger.debug(f"FileOperationBlock: Appended to {path}")
                return {
                    "success": True,
                    "path": path,
                    "status": "appended",
                }

            elif operation == "exists":
                exists = os.path.isfile(path)
                logger.debug(f"FileOperationBlock: exists({path}) = {exists}")
                return {
                    "success": True,
                    "path": path,
                    "exists": exists,
                    "status": "checked",
                }

            elif operation == "delete":
                if os.path.isfile(path):
                    os.remove(path)
                    logger.debug(f"FileOperationBlock: Deleted {path}")
                    return {"success": True, "path": path, "status": "deleted"}
                return {"success": False, "error": f"File not found: {path}"}

            return {"success": False, "error": f"Unknown operation: {operation}"}
        except Exception as e:
            return {"success": False, "error": f"FileOperationBlock: {str(e)}"}
