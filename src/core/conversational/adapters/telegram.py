"""
Telegram Conversational Adapter — Real Telegram bot integration.

Uses aiohttp directly for HTTP requests to the Telegram Bot API.
No external telegram library required.

Features:
  - Long-polling for updates
  - Message processing through the conversational engine
  - Inline keyboard for confirmations
  - Telegram MarkdownV2 formatting
  - Rate limiting (respects 30 msg/sec to one chat)
  - Command handling: /start, /help, /status, /cancel
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.conversational.adapters.telegram")

# ─── Telegram API Constants ───────────────────────────────────

TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"
RATE_LIMIT_PER_CHAT = 30  # messages per second to one chat
RATE_LIMIT_GLOBAL = 30  # messages per second globally
POLL_TIMEOUT = 30  # seconds for long-polling
POLL_ERROR_DELAY = 5  # seconds to wait after polling error
MAX_MESSAGE_LENGTH = 4096  # Telegram message limit


class TelegramAdapter:
    """Telegram bot adapter using aiohttp for HTTP calls.

    Integrates with the conversational engine for message processing
    and confirm manager for inline keyboard confirmations.
    """

    def __init__(
        self,
        token: str,
        allowed_users: Optional[List[int]] = None,
        conversation_engine: Optional[Any] = None,
        confirm_manager: Optional[Any] = None,
    ) -> None:
        """
        Args:
            token: Telegram bot token.
            allowed_users: If provided, only these user IDs can interact.
            conversation_engine: ConversationEngine instance for processing.
            confirm_manager: ConfirmManager instance for confirmation flows.
        """
        self._token = token
        self._allowed_users = allowed_users
        self._engine = conversation_engine
        self._confirm_mgr = confirm_manager
        self._running = False
        self._last_update_id = 0
        self._session: Optional[Any] = None  # aiohttp.ClientSession

        # Rate limiting
        self._chat_timestamps: Dict[int, List[float]] = {}
        self._global_timestamps: List[float] = []
        self._rate_lock = asyncio.Lock()

        # Stats
        self._stats = {
            "messages_received": 0,
            "messages_sent": 0,
            "confirmations_sent": 0,
            "callbacks_processed": 0,
            "errors": 0,
            "commands_processed": 0,
        }

    # ─── Lifecycle ─────────────────────────────────────────────

    async def start_polling(self) -> None:
        """Start the long-polling loop for Telegram updates."""
        import aiohttp

        self._running = True
        self._session = aiohttp.ClientSession()

        logger.info("Telegram adapter: starting long-polling")

        try:
            # Verify bot token
            me = await self._api_request("getMe")
            if not me or not me.get("ok"):
                logger.error("Telegram adapter: invalid bot token")
                return

            bot_name = me.get("result", {}).get("username", "unknown")
            logger.info(f"Telegram adapter: connected as @{bot_name}")

            while self._running:
                try:
                    updates = await self._poll_updates()
                    if updates:
                        for update in updates:
                            try:
                                await self._dispatch_update(update)
                            except Exception as e:
                                logger.error(f"Error dispatching update: {e}")
                                self._stats["errors"] += 1
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Polling error: {e}")
                    self._stats["errors"] += 1
                    await asyncio.sleep(POLL_ERROR_DELAY)
        finally:
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None
            logger.info("Telegram adapter: stopped")

    def stop_polling(self) -> None:
        """Stop the long-polling loop."""
        self._running = False

    # ─── Message Handling ──────────────────────────────────────

    async def handle_message(self, update: Dict) -> Dict:
        """Process incoming message through conversational engine.

        Args:
            update: Telegram Update object.

        Returns:
            Result dict with processing status.
        """
        message = update.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id", 0)
        text = message.get("text", "")

        if not text:
            return {"status": "ignored", "reason": "no_text"}

        # Check allowed users
        if self._allowed_users and user_id not in self._allowed_users:
            await self.send_response(
                chat_id,
                "Sorry, you are not authorized to use this bot.",
                "MarkdownV2",
            )
            return {"status": "rejected", "reason": "unauthorized_user"}

        self._stats["messages_received"] += 1

        # Handle commands
        if text.startswith("/"):
            return await self._handle_command(chat_id, user_id, text)

        # Process through conversation engine
        if self._engine is None:
            await self.send_response(chat_id, "Engine not available.", "MarkdownV2")
            return {"status": "error", "reason": "no_engine"}

        try:
            session_id = f"tg_{chat_id}"
            response = await self._engine.process_message(
                session_id=session_id,
                user_message=text,
            )

            # Format and send response
            formatted = self._format_markdown(response.content)
            await self.send_response(chat_id, formatted, "MarkdownV2")

            # Check if response includes a confirmation request
            # (handled by confirm_manager separately via inline keyboards)

            return {"status": "ok", "chat_id": chat_id, "source": response.metadata.source}

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            self._stats["errors"] += 1
            await self.send_response(
                chat_id,
                "I encountered an error processing your message\\. Please try again\\.",
                "MarkdownV2",
            )
            return {"status": "error", "reason": str(e)}

    # ─── Sending ───────────────────────────────────────────────

    async def send_response(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "MarkdownV2",
    ) -> bool:
        """Send formatted response to a chat.

        Handles message splitting for messages exceeding Telegram's 4096 char limit.
        Respects rate limits.

        Args:
            chat_id: Target chat ID.
            text: Message text.
            parse_mode: Parse mode (MarkdownV2, HTML, or empty).

        Returns:
            True if sent successfully, False otherwise.
        """
        # Rate limiting
        await self._respect_rate_limit(chat_id)

        # Split long messages
        messages = self._split_message(text, MAX_MESSAGE_LENGTH)

        for msg in messages:
            payload: Dict[str, Any] = {
                "chat_id": chat_id,
                "text": msg,
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode

            result = await self._api_request("sendMessage", payload)
            if result and result.get("ok"):
                self._stats["messages_sent"] += 1
            else:
                logger.warning(f"Failed to send message to chat {chat_id}")
                self._stats["errors"] += 1
                return False

        return True

    async def send_confirmation(
        self,
        chat_id: int,
        confirm_data: Dict,
    ) -> bool:
        """Send inline keyboard for confirmations.

        Args:
            chat_id: Target chat ID.
            confirm_data: Confirmation data from ConfirmManager.request_confirmation().

        Returns:
            True if sent successfully.
        """
        await self._respect_rate_limit(chat_id)

        action_id = confirm_data.get("action_id", "unknown")
        message = confirm_data.get("message", "Confirm action?")

        # Escape for MarkdownV2
        formatted_msg = self._format_markdown(message)

        payload = {
            "chat_id": chat_id,
            "text": formatted_msg,
            "parse_mode": "MarkdownV2",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {
                            "text": "✅ Confirm",
                            "callback_data": f"confirm:{action_id}:yes",
                        },
                        {
                            "text": "❌ Deny",
                            "callback_data": f"confirm:{action_id}:no",
                        },
                    ],
                    [
                        {
                            "text": "ℹ️ More Info",
                            "callback_data": f"confirm:{action_id}:more_info",
                        },
                    ],
                ],
            },
        }

        result = await self._api_request("sendMessage", payload)
        if result and result.get("ok"):
            self._stats["confirmations_sent"] += 1
            return True

        self._stats["errors"] += 1
        return False

    # ─── Callback Handling ─────────────────────────────────────

    async def handle_callback(self, callback: Dict) -> Dict:
        """Handle inline keyboard callback.

        Args:
            callback: Telegram CallbackQuery object.

        Returns:
            Result dict with processing status.
        """
        self._stats["callbacks_processed"] += 1

        callback_query_id = callback.get("id", "")
        data = callback.get("data", "")
        chat_id = callback.get("message", {}).get("chat", {}).get("id")
        user_id = callback.get("from", {}).get("id", 0)

        # Answer the callback query to remove the loading indicator
        await self._api_request("answerCallbackQuery", {
            "callback_query_id": callback_query_id,
        })

        # Parse callback data
        parts = data.split(":", 2)
        if len(parts) < 3:
            return {"status": "error", "reason": "invalid_callback_data"}

        action_type = parts[0]  # "confirm" or "approve"
        action_id = parts[1]
        user_response = parts[2]

        # Check authorization
        if self._allowed_users and user_id not in self._allowed_users:
            await self.send_response(chat_id, "Unauthorized action.", "MarkdownV2")
            return {"status": "rejected", "reason": "unauthorized"}

        # Process through confirm manager
        if self._confirm_mgr is None:
            await self.send_response(
                chat_id, "Confirmation system not available.", "MarkdownV2"
            )
            return {"status": "error", "reason": "no_confirm_manager"}

        try:
            if action_type == "confirm":
                result = self._confirm_mgr.process_response(action_id, user_response)
            elif action_type == "approve":
                approved = user_response.lower() in ("yes", "y", "approve")
                result = self._confirm_mgr.process_approval(
                    action_id, str(user_id), approved
                )
            else:
                return {"status": "error", "reason": f"unknown_action_type: {action_type}"}

            # Send result message
            result_msg = self._format_markdown(result.get("message", "Processed."))
            await self.send_response(chat_id, result_msg, "MarkdownV2")

            return {"status": "ok", "action_id": action_id, "result": result}

        except Exception as e:
            logger.error(f"Error processing callback: {e}")
            self._stats["errors"] += 1
            return {"status": "error", "reason": str(e)}

    # ─── Command Handling ──────────────────────────────────────

    async def _handle_command(
        self,
        chat_id: int,
        user_id: int,
        text: str,
    ) -> Dict:
        """Handle bot commands."""
        self._stats["commands_processed"] += 1
        command = text.split()[0].lower()
        args = text.split()[1:] if len(text.split()) > 1 else []

        if command == "/start":
            msg = (
                "👋 Hello\\! I'm the *Zenic\\-Agents* assistant\\.\n\n"
                "I can help you with:\n"
                "  • Code generation and debugging\n"
                "  • Questions and explanations\n"
                "  • Automations and business logic\n\n"
                "Type /help for available commands\\."
            )
            await self.send_response(chat_id, msg, "MarkdownV2")

        elif command == "/help":
            msg = (
                "*Available Commands:*\n\n"
                "/start \\- Start the bot\n"
                "/help \\- Show this help\n"
                "/status \\- Show system status\n"
                "/cancel \\- Cancel pending actions\n\n"
                "You can also just type your request in natural language\\!"
            )
            await self.send_response(chat_id, msg, "MarkdownV2")

        elif command == "/status":
            status_parts = ["*System Status:*\n"]
            if self._engine:
                stats = self._engine.stats
                status_parts.append(f"  Total requests: {stats.get('total_requests', 0)}")
                status_parts.append(f"  Engine calls: {stats.get('total_engine_calls', 0)}")
            else:
                status_parts.append("  Engine: not connected")

            if self._confirm_mgr:
                status_parts.append(f"  Pending confirmations: {self._confirm_mgr.pending_count}")

            msg = self._format_markdown("\n".join(status_parts))
            await self.send_response(chat_id, msg, "MarkdownV2")

        elif command == "/cancel":
            if self._confirm_mgr:
                pending = self._confirm_mgr.get_pending(f"tg_{chat_id}")
                cancelled = 0
                for p in pending:
                    if self._confirm_mgr.cancel(p["action_id"]):
                        cancelled += 1
                msg = self._format_markdown(
                    f"Cancelled {cancelled} pending action(s)\\."
                )
            else:
                msg = "No pending actions to cancel\\."
            await self.send_response(chat_id, msg, "MarkdownV2")

        else:
            msg = self._format_markdown(
                f"Unknown command: {command}\\. Type /help for available commands\\."
            )
            await self.send_response(chat_id, msg, "MarkdownV2")

        return {"status": "ok", "command": command}

    # ─── API Requests ──────────────────────────────────────────

    async def _api_request(
        self,
        method: str,
        payload: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """Make a request to the Telegram Bot API.

        Args:
            method: API method name (e.g., "sendMessage", "getUpdates").
            payload: Request payload dict.

        Returns:
            API response dict, or None on failure.
        """
        if self._session is None or self._session.closed:
            logger.error("Telegram adapter: session not available")
            return None

        url = TELEGRAM_API_BASE.format(token=self._token, method=method)

        try:
            if payload:
                async with self._session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 429:
                        # Rate limited
                        retry_after = int(resp.headers.get("Retry-After", "1"))
                        logger.warning(f"Telegram rate limited, retry after {retry_after}s")
                        await asyncio.sleep(retry_after)
                        # Retry once
                        async with self._session.post(url, json=payload) as retry_resp:
                            if retry_resp.status == 200:
                                return await retry_resp.json()
                    else:
                        body = await resp.text()
                        logger.error(f"Telegram API error: {resp.status} - {body[:200]}")
            else:
                async with self._session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    else:
                        body = await resp.text()
                        logger.error(f"Telegram API error: {resp.status} - {body[:200]}")

        except asyncio.TimeoutError:
            logger.warning(f"Telegram API timeout for {method}")
        except Exception as e:
            logger.error(f"Telegram API request error: {e}")

        return None

    async def _poll_updates(self) -> List[Dict]:
        """Long-poll for updates from Telegram."""
        payload = {
            "offset": self._last_update_id + 1,
            "timeout": POLL_TIMEOUT,
            "allowed_updates": ["message", "callback_query"],
        }

        result = await self._api_request("getUpdates", payload)
        if result and result.get("ok"):
            updates = result.get("result", [])
            if updates:
                self._last_update_id = max(u.get("update_id", 0) for u in updates)
            return updates

        return []

    async def _dispatch_update(self, update: Dict) -> None:
        """Dispatch an update to the appropriate handler."""
        if "message" in update:
            await self.handle_message(update)
        elif "callback_query" in update:
            await self.handle_callback(update)

    # ─── Rate Limiting ─────────────────────────────────────────

    async def _respect_rate_limit(self, chat_id: int) -> None:
        """Ensure we don't exceed Telegram rate limits."""
        async with self._rate_lock:
            now = time.time()

            # Clean old timestamps
            self._global_timestamps = [
                t for t in self._global_timestamps if now - t < 1.0
            ]

            if chat_id in self._chat_timestamps:
                self._chat_timestamps[chat_id] = [
                    t for t in self._chat_timestamps[chat_id] if now - t < 1.0
                ]
            else:
                self._chat_timestamps[chat_id] = []

            # Wait if needed
            while (
                len(self._global_timestamps) >= RATE_LIMIT_GLOBAL
                or len(self._chat_timestamps.get(chat_id, [])) >= RATE_LIMIT_PER_CHAT
            ):
                await asyncio.sleep(0.05)
                now = time.time()
                self._global_timestamps = [
                    t for t in self._global_timestamps if now - t < 1.0
                ]
                self._chat_timestamps[chat_id] = [
                    t for t in self._chat_timestamps.get(chat_id, [])
                    if now - t < 1.0
                ]

            # Record timestamp
            self._global_timestamps.append(now)
            self._chat_timestamps[chat_id].append(now)

    # ─── Formatting ────────────────────────────────────────────

    @staticmethod
    def _format_markdown(text: str) -> str:
        """Format text for Telegram MarkdownV2.

        MarkdownV2 requires escaping: _ * [ ] ( ) ~ ` > # + - = | { } . !
        Code blocks (```) are preserved without internal escaping.
        """
        if not text:
            return ""

        # Preserve code blocks using alphanumeric-only placeholders
        code_blocks: list[str] = []
        def _save_code(match: re.Match) -> str:
            code_blocks.append(match.group(0))
            return f"ZENICTGCODE{len(code_blocks) - 1}ENDZENIC"

        text = re.sub(r'```[\s\S]*?```', _save_code, text)

        # Preserve inline code
        inline_codes: list[str] = []
        def _save_inline(match: re.Match) -> str:
            inline_codes.append(match.group(0))
            return f"ZENICTGINLINE{len(inline_codes) - 1}ENDZENIC"

        text = re.sub(r'`[^`]+`', _save_inline, text)

        # Escape special MarkdownV2 characters
        special_chars = r'_*[]()~>#+-=|{}.!'
        for char in special_chars:
            text = text.replace(char, f'\\{char}')

        # Restore inline code
        for i, code in enumerate(inline_codes):
            text = text.replace(f"ZENICTGINLINE{i}ENDZENIC", code)

        # Restore code blocks
        for i, block in enumerate(code_blocks):
            text = text.replace(f"ZENICTGCODE{i}ENDZENIC", block)

        return text

    @staticmethod
    def _split_message(text: str, max_length: int) -> List[str]:
        """Split text into chunks that fit within Telegram's message limit.

        Tries to split on paragraph boundaries, then on line boundaries,
        then on word boundaries.
        """
        if len(text) <= max_length:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break

            # Try paragraph boundary
            split_at = remaining.rfind("\n\n", 0, max_length)
            if split_at < max_length // 2:
                # Try line boundary
                split_at = remaining.rfind("\n", 0, max_length)
            if split_at < max_length // 2:
                # Try word boundary
                split_at = remaining.rfind(" ", 0, max_length)
            if split_at < max_length // 2:
                # Hard split
                split_at = max_length

            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip("\n")

        return chunks

    # ─── Properties ────────────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """Adapter statistics."""
        return {**self._stats}

    @property
    def is_running(self) -> bool:
        """Whether the adapter is currently polling."""
        return self._running
