"""
Discord Conversational Adapter — Real Discord bot integration.

Uses aiohttp directly for Discord REST API calls.
No discord.py required.

Features:
  - Gateway connection for receiving events
  - REST API for sending messages and interactions
  - Embed-based responses for rich formatting
  - Button-based confirmations
  - Rate limiting (respects Discord rate limits)
  - Command handling: /zenic, /status, /confirm, /cancel
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("zenic_agents.conversational.adapters.discord")

# ─── Discord API Constants ────────────────────────────────────

DISCORD_API_BASE = "https://discord.com/api/v10"
GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
MAX_EMBED_DESCRIPTION = 4096
MAX_MESSAGE_LENGTH = 2000
HEARTBEAT_INTERVAL_DEFAULT = 41.25  # seconds


class DiscordAdapter:
    """Discord bot adapter using aiohttp for REST and Gateway.

    Integrates with the conversational engine for message processing
    and confirm manager for button-based confirmations.
    """

    def __init__(
        self,
        token: str,
        guild_id: Optional[str] = None,
        conversation_engine: Optional[Any] = None,
        confirm_manager: Optional[Any] = None,
    ) -> None:
        """
        Args:
            token: Discord bot token.
            guild_id: If provided, only process messages from this guild.
            conversation_engine: ConversationEngine instance for processing.
            confirm_manager: ConfirmManager instance for confirmation flows.
        """
        self._token = token
        self._guild_id = guild_id
        self._engine = conversation_engine
        self._confirm_mgr = confirm_manager
        self._running = False
        self._session: Optional[Any] = None  # aiohttp.ClientSession
        self._ws: Optional[Any] = None  # aiohttp.ClientWebSocketResponse
        self._heartbeat_interval = HEARTBEAT_INTERVAL_DEFAULT
        self._sequence: Optional[int] = None
        self._session_id: Optional[str] = None
        self._application_id: Optional[str] = None
        self._bot_user_id: Optional[str] = None

        # Rate limiting
        self._rate_buckets: Dict[str, List[float]] = {}
        self._rate_lock = asyncio.Lock()

        # Stats
        self._stats = {
            "messages_received": 0,
            "messages_sent": 0,
            "confirmations_sent": 0,
            "interactions_processed": 0,
            "errors": 0,
            "commands_processed": 0,
            "reconnects": 0,
        }

    # ─── Lifecycle ─────────────────────────────────────────────

    async def start(self) -> None:
        """Start the Discord gateway connection."""
        import aiohttp

        self._running = True
        self._session = aiohttp.ClientSession()

        logger.info("Discord adapter: connecting to gateway")

        try:
            # Get gateway URL
            gateway_resp = await self._api_request("GET", "/gateway/bot")
            if gateway_resp and "url" in gateway_resp:
                gateway_url = gateway_resp["url"] + "?v=10&encoding=json"
            else:
                gateway_url = GATEWAY_URL

            while self._running:
                try:
                    await self._connect_and_listen(gateway_url)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Discord gateway error: {e}")
                    self._stats["errors"] += 1
                    if self._running:
                        self._stats["reconnects"] += 1
                        await asyncio.sleep(5)

        finally:
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None
            logger.info("Discord adapter: stopped")

    def stop(self) -> None:
        """Stop the Discord adapter."""
        self._running = False

    async def _connect_and_listen(self, gateway_url: str) -> None:
        """Connect to the Discord gateway and listen for events."""
        import aiohttp

        async with self._session.ws_connect(gateway_url) as ws:
            self._ws = ws

            # Receive Hello
            hello = await ws.receive_json()
            if hello.get("op") != 10:
                logger.error(f"Expected Hello op=10, got op={hello.get('op')}")
                return

            self._heartbeat_interval = hello["d"]["heartbeat_interval"] / 1000.0

            # Identify or Resume
            if self._session_id and self._sequence is not None:
                await self._send_resume(ws)
            else:
                await self._send_identify(ws)

            # Start heartbeat
            heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws))

            try:
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        await self._handle_gateway_event(data)
                    elif msg.type in (
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    ):
                        break
            finally:
                heartbeat_task.cancel()
                self._ws = None

    async def _send_identify(self, ws: Any) -> None:
        """Send Identify payload to the gateway."""
        payload = {
            "op": 2,
            "d": {
                "token": self._token,
                "intents": (1 << 9) | (1 << 15),  # GUILD_MESSAGES + MESSAGE_CONTENT
                "properties": {
                    "os": "linux",
                    "browser": "zenic-agents",
                    "device": "zenic-agents",
                },
            },
        }
        if self._guild_id:
            payload["d"]["guild_id"] = [self._guild_id]  # Server-only

        await ws.send_json(payload)
        logger.debug("Discord: Identified")

    async def _send_resume(self, ws: Any) -> None:
        """Send Resume payload to the gateway."""
        payload = {
            "op": 6,
            "d": {
                "token": self._token,
                "session_id": self._session_id,
                "seq": self._sequence,
            },
        }
        await ws.send_json(payload)
        logger.debug("Discord: Resuming session")

    async def _heartbeat_loop(self, ws: Any) -> None:
        """Send heartbeats at the required interval."""
        while self._running:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                payload = {
                    "op": 1,
                    "d": self._sequence,
                }
                await ws.send_json(payload)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat error: {e}")
                break

    async def _handle_gateway_event(self, data: Dict) -> None:
        """Handle a gateway event."""
        op = data.get("op")
        d = data.get("d", {})
        t = data.get("t")
        s = data.get("s")

        if s is not None:
            self._sequence = s

        # Dispatch
        if op == 0:  # Dispatch
            if t == "READY":
                self._session_id = d.get("session_id")
                self._bot_user_id = d.get("user", {}).get("id")
                self._application_id = d.get("application", {}).get("id")
                bot_name = d.get("user", {}).get("username", "unknown")
                logger.info(f"Discord adapter: connected as {bot_name}")

                # Register slash commands
                await self._register_commands()

            elif t == "MESSAGE_CREATE":
                await self.handle_message(d)

            elif t == "INTERACTION_CREATE":
                await self.handle_interaction(d)

        elif op == 7:  # Reconnect
            logger.info("Discord: Reconnect requested")
            self._stats["reconnects"] += 1

        elif op == 9:  # Invalid Session
            logger.warning("Discord: Invalid session, re-identifying")
            self._session_id = None
            self._sequence = None

        elif op == 11:  # Heartbeat ACK
            pass  # Good, connection alive

    # ─── Slash Commands ────────────────────────────────────────

    async def _register_commands(self) -> None:
        """Register slash commands with Discord."""
        if not self._application_id:
            return

        commands = [
            {
                "name": "zenic",
                "description": "Send a message to the Zenic-Agents assistant",
                "options": [
                    {
                        "name": "message",
                        "description": "Your message or request",
                        "type": 3,  # STRING
                        "required": True,
                    }
                ],
            },
            {
                "name": "status",
                "description": "Show Zenic-Agents system status",
            },
            {
                "name": "confirm",
                "description": "Confirm or deny a pending action",
                "options": [
                    {
                        "name": "action_id",
                        "description": "The action ID to confirm",
                        "type": 3,
                        "required": True,
                    },
                    {
                        "name": "response",
                        "description": "yes or no",
                        "type": 3,
                        "required": True,
                        "choices": [
                            {"name": "Yes", "value": "yes"},
                            {"name": "No", "value": "no"},
                        ],
                    },
                ],
            },
            {
                "name": "cancel",
                "description": "Cancel all pending actions",
            },
        ]

        endpoint = f"/applications/{self._application_id}/commands"
        if self._guild_id:
            endpoint = f"/applications/{self._application_id}/guilds/{self._guild_id}/commands"

        await self._api_request("PUT", endpoint, json_data=commands)
        logger.debug("Discord: Slash commands registered")

    # ─── Message Handling ──────────────────────────────────────

    async def handle_message(self, message: Dict) -> Dict:
        """Process incoming message through conversational engine.

        Args:
            message: Discord Message object.

        Returns:
            Result dict with processing status.
        """
        # Ignore own messages
        author_id = message.get("author", {}).get("id", "")
        if author_id == self._bot_user_id:
            return {"status": "ignored", "reason": "own_message"}

        # Ignore bot messages
        if message.get("author", {}).get("bot", False):
            return {"status": "ignored", "reason": "bot_message"}

        content = message.get("content", "")
        channel_id = message.get("channel_id", "")
        guild_id = message.get("guild_id", "")

        # Check guild filter
        if self._guild_id and guild_id != self._guild_id:
            return {"status": "ignored", "reason": "wrong_guild"}

        # Only process messages that mention the bot or are DMs
        mentions = message.get("mentions", [])
        is_dm = not guild_id
        is_mentioned = any(m.get("id") == self._bot_user_id for m in mentions)

        if not is_dm and not is_mentioned:
            return {"status": "ignored", "reason": "not_mentioned"}

        # Strip bot mention from content
        clean_content = re.sub(r'<@!?\d+>', '', content).strip()
        if not clean_content:
            return {"status": "ignored", "reason": "empty_after_mention_strip"}

        self._stats["messages_received"] += 1

        # Process through conversation engine
        if self._engine is None:
            await self.send_response(
                channel_id, "Engine not available.", title="Error"
            )
            return {"status": "error", "reason": "no_engine"}

        try:
            session_id = f"dc_{channel_id}"
            response = await self._engine.process_message(
                session_id=session_id,
                user_message=clean_content,
            )

            await self.send_response(
                channel_id, response.content,
                title="Zenic-Agents" if len(response.content) > 200 else None,
            )

            return {
                "status": "ok",
                "channel_id": channel_id,
                "source": response.metadata.source,
            }

        except Exception as e:
            logger.error(f"Error processing Discord message: {e}")
            self._stats["errors"] += 1
            await self.send_response(
                channel_id,
                "I encountered an error processing your message. Please try again.",
                title="Error",
            )
            return {"status": "error", "reason": str(e)}

    # ─── Sending ───────────────────────────────────────────────

    async def send_response(
        self,
        channel_id: str,
        text: str,
        title: Optional[str] = None,
    ) -> bool:
        """Send response to a Discord channel.

        Uses embeds for responses with titles, plain messages otherwise.

        Args:
            channel_id: Target channel ID.
            text: Response text.
            title: Optional embed title.

        Returns:
            True if sent successfully.
        """
        # Rate limiting
        await self._respect_rate_limit(channel_id)

        # Truncate if needed
        if len(text) > MAX_EMBED_DESCRIPTION:
            text = text[:MAX_EMBED_DESCRIPTION - 3] + "..."

        if title:
            payload = {
                "embeds": [self._format_embed(text, title)],
            }
        else:
            # Split plain messages if too long
            if len(text) > MAX_MESSAGE_LENGTH:
                chunks = self._split_message(text, MAX_MESSAGE_LENGTH)
                success = True
                for chunk in chunks:
                    result = await self._send_channel_message(channel_id, chunk)
                    if not result:
                        success = False
                return success
            return await self._send_channel_message(channel_id, text)

        endpoint = f"/channels/{channel_id}/messages"
        result = await self._api_request("POST", endpoint, json_data=payload)
        if result:
            self._stats["messages_sent"] += 1
            return True

        self._stats["errors"] += 1
        return False

    async def _send_channel_message(self, channel_id: str, text: str) -> bool:
        """Send a plain text message to a channel."""
        endpoint = f"/channels/{channel_id}/messages"
        payload = {"content": text}
        result = await self._api_request("POST", endpoint, json_data=payload)
        if result:
            self._stats["messages_sent"] += 1
            return True
        self._stats["errors"] += 1
        return False

    async def send_confirmation(
        self,
        channel_id: str,
        confirm_data: Dict,
    ) -> bool:
        """Send button-based confirmation to a channel.

        Args:
            channel_id: Target channel ID.
            confirm_data: Confirmation data from ConfirmManager.

        Returns:
            True if sent successfully.
        """
        await self._respect_rate_limit(channel_id)

        action_id = confirm_data.get("action_id", "unknown")
        message = confirm_data.get("message", "Confirm action?")

        # Truncate message for embed
        if len(message) > MAX_EMBED_DESCRIPTION:
            message = message[:MAX_EMBED_DESCRIPTION - 3] + "..."

        custom_id_prefix = f"zenic_confirm_{action_id}"

        payload = {
            "embeds": [{
                "title": "⚠️ Confirmation Required",
                "description": message,
                "color": 16776960,  # Yellow
            }],
            "components": [
                {
                    "type": 1,  # Action Row
                    "components": [
                        {
                            "type": 2,  # Button
                            "style": 3,  # Success (green)
                            "label": "✅ Confirm",
                            "custom_id": f"{custom_id_prefix}:yes",
                        },
                        {
                            "type": 2,
                            "style": 4,  # Danger (red)
                            "label": "❌ Deny",
                            "custom_id": f"{custom_id_prefix}:no",
                        },
                        {
                            "type": 2,
                            "style": 2,  # Secondary (gray)
                            "label": "ℹ️ More Info",
                            "custom_id": f"{custom_id_prefix}:more_info",
                        },
                    ],
                },
            ],
        }

        endpoint = f"/channels/{channel_id}/messages"
        result = await self._api_request("POST", endpoint, json_data=payload)
        if result:
            self._stats["confirmations_sent"] += 1
            return True

        self._stats["errors"] += 1
        return False

    # ─── Interaction Handling ──────────────────────────────────

    async def handle_interaction(self, interaction: Dict) -> Dict:
        """Handle button interactions and slash commands.

        Args:
            interaction: Discord Interaction object.

        Returns:
            Result dict with processing status.
        """
        self._stats["interactions_processed"] += 1

        interaction_type = interaction.get("type", 0)
        interaction_id = interaction.get("id", "")
        interaction_token = interaction.get("token", "")

        # Slash command (type 2)
        if interaction_type == 2:
            return await self._handle_slash_command(interaction)

        # Button interaction (type 3)
        elif interaction_type == 3:
            return await self._handle_button_interaction(interaction)

        return {"status": "ignored", "reason": f"unknown_interaction_type: {interaction_type}"}

    async def _handle_slash_command(self, interaction: Dict) -> Dict:
        """Handle a slash command interaction."""
        self._stats["commands_processed"] += 1

        data = interaction.get("data", {})
        command_name = data.get("name", "")
        interaction_id = interaction.get("id", "")
        interaction_token = interaction.get("token", "")
        channel_id = interaction.get("channel_id", "")
        user_id = interaction.get("member", {}).get("user", {}).get("id", "")

        options = {opt["name"]: opt["value"] for opt in data.get("options", [])}

        if command_name == "zenic":
            message = options.get("message", "")

            # Acknowledge the interaction
            await self._api_request(
                "POST",
                f"/interactions/{interaction_id}/{interaction_token}/callback",
                json_data={"type": 5},  # Deferred
            )

            # Process through engine
            if self._engine and message:
                try:
                    session_id = f"dc_{channel_id}"
                    response = await self._engine.process_message(
                        session_id=session_id,
                        user_message=message,
                    )

                    # Follow up with response
                    await self._api_request(
                        "POST",
                        f"/webhooks/{self._application_id}/{interaction_token}",
                        json_data={
                            "content": response.content[:MAX_MESSAGE_LENGTH],
                        },
                    )

                    return {"status": "ok", "command": "zenic"}
                except Exception as e:
                    logger.error(f"Error processing /zenic command: {e}")

            return {"status": "error", "command": "zenic"}

        elif command_name == "status":
            status_parts = ["**Zenic-Agents Status:**\n"]
            if self._engine:
                stats = self._engine.stats
                status_parts.append(f"  Total requests: {stats.get('total_requests', 0)}")
                status_parts.append(f"  Engine calls: {stats.get('total_engine_calls', 0)}")
            else:
                status_parts.append("  Engine: not connected")

            if self._confirm_mgr:
                status_parts.append(f"  Pending confirmations: {self._confirm_mgr.pending_count}")

            await self._respond_interaction(interaction_id, interaction_token, "\n".join(status_parts))
            return {"status": "ok", "command": "status"}

        elif command_name == "confirm":
            action_id = options.get("action_id", "")
            response = options.get("response", "no")

            if self._confirm_mgr:
                result = self._confirm_mgr.process_response(action_id, response)
                await self._respond_interaction(
                    interaction_id, interaction_token,
                    result.get("message", "Processed.")
                )
            else:
                await self._respond_interaction(
                    interaction_id, interaction_token,
                    "Confirmation system not available."
                )

            return {"status": "ok", "command": "confirm"}

        elif command_name == "cancel":
            if self._confirm_mgr:
                pending = self._confirm_mgr.get_pending(f"dc_{channel_id}")
                cancelled = sum(
                    1 for p in pending if self._confirm_mgr.cancel(p["action_id"])
                )
                msg = f"Cancelled {cancelled} pending action(s)."
            else:
                msg = "No pending actions to cancel."

            await self._respond_interaction(interaction_id, interaction_token, msg)
            return {"status": "ok", "command": "cancel"}

        return {"status": "unknown_command", "command": command_name}

    async def _handle_button_interaction(self, interaction: Dict) -> Dict:
        """Handle a button interaction (confirmation buttons)."""
        data = interaction.get("data", {})
        custom_id = data.get("custom_id", "")
        interaction_id = interaction.get("id", "")
        interaction_token = interaction.get("token", "")
        user_id = interaction.get("member", {}).get("user", {}).get("id", "")

        # Parse custom_id: zenic_confirm_{action_id}:{response}
        match = re.match(r"zenic_confirm_(.+):(.+)", custom_id)
        if not match:
            await self._respond_interaction(interaction_id, interaction_token, "Unknown action.")
            return {"status": "error", "reason": "invalid_custom_id"}

        action_id = match.group(1)
        user_response = match.group(2)

        if self._confirm_mgr is None:
            await self._respond_interaction(
                interaction_id, interaction_token,
                "Confirmation system not available."
            )
            return {"status": "error", "reason": "no_confirm_manager"}

        result = self._confirm_mgr.process_response(action_id, user_response)
        await self._respond_interaction(
            interaction_id, interaction_token,
            result.get("message", "Processed.")
        )

        return {"status": "ok", "action_id": action_id, "result": result}

    async def _respond_interaction(
        self,
        interaction_id: str,
        interaction_token: str,
        message: str,
    ) -> None:
        """Respond to an interaction with a message."""
        payload = {
            "type": 4,  # ChannelMessageWithSource
            "data": {
                "content": message[:MAX_MESSAGE_LENGTH],
                "flags": 64,  # Ephemeral (only visible to user)
            },
        }
        endpoint = f"/interactions/{interaction_id}/{interaction_token}/callback"
        await self._api_request("POST", endpoint, json_data=payload)

    # ─── API Requests ──────────────────────────────────────────

    async def _api_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """Make a request to the Discord REST API.

        Args:
            method: HTTP method (GET, POST, PUT, PATCH, DELETE).
            endpoint: API endpoint path (e.g., "/channels/123/messages").
            json_data: Optional JSON body.

        Returns:
            Response dict, or None on failure.
        """
        if self._session is None or self._session.closed:
            logger.error("Discord adapter: session not available")
            return None

        url = DISCORD_API_BASE + endpoint
        headers = {
            "Authorization": f"Bot {self._token}",
            "Content-Type": "application/json",
        }

        try:
            async with self._session.request(
                method, url, headers=headers, json=json_data,
            ) as resp:
                # Handle rate limiting
                remaining = resp.headers.get("X-RateLimit-Remaining", "")
                reset_after = resp.headers.get("X-RateLimit-Reset-After", "")

                if resp.status == 429:
                    retry_after = float(reset_after) if reset_after else 5.0
                    logger.warning(f"Discord rate limited, retry after {retry_after}s")
                    await asyncio.sleep(retry_after)
                    # Retry once
                    async with self._session.request(
                        method, url, headers=headers, json=json_data,
                    ) as retry_resp:
                        if retry_resp.status in (200, 201, 204):
                            if retry_resp.status == 204:
                                return {}
                            return await retry_resp.json()
                        return None

                elif resp.status in (200, 201):
                    return await resp.json()
                elif resp.status == 204:
                    return {}
                else:
                    body = await resp.text()
                    logger.error(f"Discord API error: {resp.status} - {body[:200]}")
                    return None

        except asyncio.TimeoutError:
            logger.warning(f"Discord API timeout for {method} {endpoint}")
        except Exception as e:
            logger.error(f"Discord API request error: {e}")

        return None

    # ─── Rate Limiting ─────────────────────────────────────────

    async def _respect_rate_limit(self, channel_id: str) -> None:
        """Simple client-side rate limiting for message sends."""
        async with self._rate_lock:
            now = time.time()

            if channel_id not in self._rate_buckets:
                self._rate_buckets[channel_id] = []

            # Clean old timestamps (keep last 1 second)
            self._rate_buckets[channel_id] = [
                t for t in self._rate_buckets[channel_id] if now - t < 1.0
            ]

            # Discord: 5 messages per 5 seconds per channel
            while len(self._rate_buckets[channel_id]) >= 5:
                await asyncio.sleep(0.2)
                now = time.time()
                self._rate_buckets[channel_id] = [
                    t for t in self._rate_buckets[channel_id] if now - t < 5.0
                ]

            self._rate_buckets[channel_id].append(now)

    # ─── Formatting ────────────────────────────────────────────

    @staticmethod
    def _format_embed(text: str, title: str) -> Dict:
        """Format a Discord embed.

        Args:
            text: Embed description.
            title: Embed title.

        Returns:
            Discord embed dict.
        """
        # Truncate description
        if len(text) > MAX_EMBED_DESCRIPTION:
            text = text[:MAX_EMBED_DESCRIPTION - 3] + "..."

        return {
            "title": title[:256],  # Discord title limit
            "description": text,
            "color": 5814783,  # Blue
        }

    @staticmethod
    def _split_message(text: str, max_length: int) -> List[str]:
        """Split text into chunks within Discord's message limit."""
        if len(text) <= max_length:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= max_length:
                chunks.append(remaining)
                break

            split_at = remaining.rfind("\n", 0, max_length)
            if split_at < max_length // 2:
                split_at = remaining.rfind(" ", 0, max_length)
            if split_at < max_length // 2:
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
        """Whether the adapter is currently connected."""
        return self._running
