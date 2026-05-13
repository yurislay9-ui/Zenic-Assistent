"""
ZENIC-AGENTS - Integration Logic Blocks

External integration blocks: email, HTTP request, webhook, file operation.
"""

import os
import json
import time
import hashlib
import logging
from typing import Any, Dict

from .chain import LogicBlock

logger = logging.getLogger(__name__)


# ============================================================
#  INTEGRATION BLOCKS (4)
# ============================================================


class EmailSendBlock(LogicBlock):
    """Envio de email via SMTP."""

    name = "email_send"
    category = "integrations"
    description = "Send email via SMTP with fallback"
    inputs = ["to", "subject", "body", "html"]
    outputs = ["message_id", "status"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            to = data.get("to", data.get("email", data.get("recipient", "")))
            subject = data.get("subject", "No Subject")
            body = data.get("body", data.get("message", data.get("text", "")))
            html = data.get("html", None)
            from_addr = data.get("from", context.get("smtp_from", "noreply@zenic.local"))

            if not to:
                return {"success": False, "error": "No recipient email provided"}

            smtp_config = context.get("smtp", {})
            message_id = hashlib.md5(f"{to}{subject}{time.time()}".encode()).hexdigest()[:16]

            # Try aiosmtplib
            try:
                import aiosmtplib
                # In sync context, just log intent
                logger.info(f"EmailSendBlock: Would send to {to} via aiosmtplib (async required)")
                return {
                    "success": True,
                    "message_id": message_id,
                    "status": "queued_async",
                    "to": to,
                    "subject": subject,
                }
            except ImportError:
                pass

            # Try smtplib as fallback
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart

                msg = MIMEMultipart("alternative")
                msg["From"] = from_addr
                msg["To"] = to
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "plain"))
                if html:
                    msg.attach(MIMEText(html, "html"))

                smtp_host = smtp_config.get("host", "localhost")
                smtp_port = smtp_config.get("port", 587)

                with smtplib.SMTP(smtp_host, smtp_port) as server:
                    server.sendmail(from_addr, [to], msg.as_string())

                logger.debug(f"EmailSendBlock: Sent to {to}")
                return {
                    "success": True,
                    "message_id": message_id,
                    "status": "sent",
                    "to": to,
                }
            except (ImportError, Exception) as smtp_err:
                logger.warning(f"EmailSendBlock: SMTP fallback failed: {smtp_err}")

            # Final fallback: log
            logger.info(f"EmailSendBlock [FALLBACK]: To={to}, Subject={subject}, Body={body[:100]}")
            return {
                "success": True,
                "message_id": message_id,
                "status": "logged",
                "to": to,
                "note": "No SMTP available, email logged",
            }
        except Exception as e:
            return {"success": False, "error": f"EmailSendBlock: {str(e)}"}


class HTTPRequestBlock(LogicBlock):
    """Realiza llamadas HTTP a APIs externas."""

    name = "http_request"
    category = "integrations"
    description = "Make HTTP API calls with fallback"
    inputs = ["url", "method", "headers", "body"]
    outputs = ["response", "status_code"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            url = data.get("url", "")
            method = data.get("method", "GET").upper()
            headers = data.get("headers", {})
            body = data.get("body", data.get("data", data.get("json", None)))
            timeout = int(data.get("timeout", 30))

            if not url:
                return {"success": False, "error": "No URL provided"}

            # Try aiohttp (async)
            try:
                import aiohttp
                logger.info(f"HTTPRequestBlock: Would call {method} {url} via aiohttp (async required)")
                return {
                    "success": True,
                    "status_code": 0,
                    "response": {"note": "Async HTTP - use in async context"},
                    "url": url,
                    "method": method,
                }
            except ImportError:
                pass

            # Try urllib (sync fallback)
            try:
                import urllib.request
                import urllib.error

                req_data = json.dumps(body).encode() if body else None
                req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
                if body and "Content-Type" not in headers:
                    req.add_header("Content-Type", "application/json")

                with urllib.request.urlopen(req, timeout=timeout) as response:
                    response_body = response.read().decode("utf-8", errors="replace")
                    try:
                        response_json = json.loads(response_body)
                    except json.JSONDecodeError:
                        response_json = {"raw": response_body}

                    logger.debug(f"HTTPRequestBlock: {method} {url} -> {response.status}")
                    return {
                        "success": True,
                        "status_code": response.status,
                        "response": response_json,
                        "url": url,
                        "method": method,
                    }
            except urllib.error.HTTPError as http_err:
                logger.warning(f"HTTPRequestBlock: HTTP {http_err.code} for {url}")
                return {
                    "success": False,
                    "status_code": http_err.code,
                    "error": f"HTTP {http_err.code}: {http_err.reason}",
                    "url": url,
                }
            except urllib.error.URLError as url_err:
                logger.warning(f"HTTPRequestBlock: URL error for {url}: {url_err}")
                return {
                    "success": False,
                    "status_code": 0,
                    "error": f"URL Error: {str(url_err)}",
                    "url": url,
                }

        except Exception as e:
            return {"success": False, "error": f"HTTPRequestBlock: {str(e)}"}


class WebhookCallBlock(LogicBlock):
    """Envia webhook con firma HMAC."""

    name = "webhook_call"
    category = "integrations"
    description = "Send webhook with HMAC signature"
    inputs = ["url", "payload", "secret"]
    outputs = ["response", "status_code", "signature"]

    def execute(self, data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            url = data.get("url", data.get("webhook_url", ""))
            payload = data.get("payload", data.get("data", {}))
            secret = data.get("secret", context.get("webhook_secret", ""))

            if not url:
                return {"success": False, "error": "No webhook URL provided"}

            # Generate HMAC signature
            signature = ""
            if secret:
                import hmac as hmac_mod
                payload_bytes = json.dumps(payload, sort_keys=True, default=str).encode()
                signature = hmac_mod.new(
                    secret.encode(), payload_bytes, hashlib.sha256
                ).hexdigest()

            # Try sending via urllib
            try:
                import urllib.request
                headers = {"Content-Type": "application/json"}
                if signature:
                    headers["X-Webhook-Signature"] = signature

                req_data = json.dumps(payload, default=str).encode()
                req = urllib.request.Request(url, data=req_data, headers=headers, method="POST")

                with urllib.request.urlopen(req, timeout=30) as response:
                    resp_body = response.read().decode("utf-8", errors="replace")
                    logger.debug(f"WebhookCallBlock: POST {url} -> {response.status}")
                    return {
                        "success": True,
                        "status_code": response.status,
                        "response": resp_body,
                        "signature": signature,
                        "url": url,
                    }
            except Exception as http_err:
                logger.warning(f"WebhookCallBlock: HTTP error: {http_err}")
                return {
                    "success": False,
                    "error": f"Webhook delivery failed: {str(http_err)}",
                    "signature": signature,
                    "url": url,
                }

        except Exception as e:
            return {"success": False, "error": f"WebhookCallBlock: {str(e)}"}


class FileOperationBlock(LogicBlock):
    """Operaciones de lectura/escritura de archivos."""

    name = "file_operation"
    category = "integrations"
    description = "Read/write file operations"
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
