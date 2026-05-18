"""Helper methods extracted from graph_api."""

from __future__ import annotations

import asyncio
import time
import uuid

import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


    def _dry_run_response(
        self,
        to: List[str],
        subject: str,
        payload: Dict[str, Any],
        reason: str,
    ) -> Dict[str, Any]:
        """Build a dry-run response (not actually sent)."""
        self._dry_run_count += 1
        dry_run_id = f"dry-run-{uuid.uuid4().hex[:12]}"

        logger.info(
            "GraphAPIEmailProvider: Dry-run send (reason=%s) to=%s subject='%s'",
            reason, to, subject[:50],
        )

        return {
            "success": True,
            "message_id": dry_run_id,
            "dry_run": True,
            "dry_run_reason": reason,
            "status_code": 0,
            "recipients": to,
            "subject": subject,
        }

    # ── Private: Large Attachment Upload ──────────────────────

    async def _upload_attachment_session(
        self,
        sender: str,
        attachment: Dict[str, Any],
    ) -> Optional[str]:
        """Upload a large attachment using a Graph API upload session.

        For attachments larger than 4MB, creates an upload session
        and uploads the file in chunks.

        Args:
            sender: Sender email for endpoint construction.
            attachment: Attachment dict with name, content_bytes, size, content_type.

        Returns:
            Attachment ID if successful, None otherwise.
        """
        file_name = attachment.get("name", "attachment")
        file_size = attachment.get("size", 0)
        content_type = attachment.get("content_type", "application/octet-stream")

        if sender:
            endpoint = f"{_GRAPH_BASE_URL}/users/{sender}/messages/attachments/createUploadSession"
        else:
            endpoint = f"{_GRAPH_BASE_URL}/me/messages/attachments/createUploadSession"

        try:
            async with self._lock:
                token = await self._token_manager.get_token(self._service_name)

            if not token.access_token or token.is_expired:
                logger.warning("GraphAPIEmailProvider: Cannot upload attachment — no valid token")
                return None

            async with aiohttp.ClientSession() as session:
                headers = {
                    "Authorization": token.authorization_header,
                    "Content-Type": "application/json",
                }

                # Create upload session
                upload_body = {
                    "AttachmentItem": {
                        "attachmentType": "file",
                        "name": file_name,
                        "size": file_size,
                        "contentType": content_type,
                    }
                }

                async with session.post(
                    endpoint,
                    json=upload_body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status not in (200, 201):
                        error_body = await response.json()
                        logger.warning(
                            "GraphAPIEmailProvider: Failed to create upload session: %s",
                            error_body.get("error", {}).get("message", response.status),
                        )
                        return None

                    session_data = await response.json()
                    upload_url = session_data.get("uploadUrl", "")

                if not upload_url:
                    logger.warning("GraphAPIEmailProvider: No upload URL in session response")
                    return None

                # Upload file in chunks (4 MB chunks)
                content_bytes = attachment.get("content_bytes", b"")
                chunk_size = 4 * 1024 * 1024
                offset = 0

                while offset < len(content_bytes):
                    chunk = content_bytes[offset:offset + chunk_size]
                    chunk_len = len(chunk)
                    content_range = f"bytes {offset}-{offset + chunk_len - 1}/{file_size}"

                    async with session.put(
                        upload_url,
                        data=chunk,
                        headers={
                            "Content-Length": str(chunk_len),
                            "Content-Range": content_range,
                        },
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as put_response:
                        if put_response.status not in (200, 201, 202):
                            logger.warning(
                                "GraphAPIEmailProvider: Chunk upload failed at offset %d: HTTP %d",
                                offset, put_response.status,
                            )
                            return None

                        if put_response.status in (200, 201):
                            # Upload complete
                            result = await put_response.json()
                            return result.get("id", "uploaded")

                    offset += chunk_len

                return "uploaded"

        except Exception as exc:
            logger.warning(
                "GraphAPIEmailProvider: Attachment upload session failed: %s", exc,
            )
            return None

