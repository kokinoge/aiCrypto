from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable

import discord

from src.config import BotConfig
from src.signals.engine import Signal, SignalEngine

logger = logging.getLogger("trading_bot")


class NansenDiscordMonitor:
    """Monitors a Discord channel for Nansen Smart Alert messages and emits signals."""

    def __init__(
        self,
        config: BotConfig,
        signal_engine: SignalEngine,
        on_signal: Callable[[Signal], Awaitable[None]],
        on_command: Callable[[str, discord.Message], Awaitable[None]] | None = None,
    ):
        self._config = config
        self._engine = signal_engine
        self._on_signal = on_signal
        self._on_command = on_command

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)

        self._setup_handlers()

    def _setup_handlers(self) -> None:
        @self._client.event
        async def on_ready():
            logger.info("Discord monitor connected as %s", self._client.user)
            channel = self._client.get_channel(self._config.discord_nansen_channel_id)
            if channel:
                logger.info("Watching channel: #%s", channel.name)
            else:
                logger.warning(
                    "Nansen channel ID %d not found — check DISCORD_NANSEN_CHANNEL_ID",
                    self._config.discord_nansen_channel_id,
                )

        @self._client.event
        async def on_message(message: discord.Message):
            if message.author == self._client.user:
                return

            # Handle ! commands in the notify channel
            if (
                message.channel.id == self._config.discord_notify_channel_id
                and message.content.startswith("!")
                and self._on_command
            ):
                cmd = message.content.strip().split()[0].lower()
                logger.debug("Command received: %s", cmd)
                try:
                    await self._on_command(cmd, message)
                except Exception:
                    logger.exception("Error handling command: %s", cmd)
                return

            # Handle Nansen signals in the nansen channel
            if message.channel.id != self._config.discord_nansen_channel_id:
                return

            logger.debug("Nansen alert received: %s", message.content[:200])

            content = message.content
            if message.embeds:
                for embed in message.embeds:
                    if embed.title:
                        content += f" {embed.title}"
                    if embed.description:
                        content += f" {embed.description}"
                    for field in embed.fields:
                        content += f" {field.name} {field.value}"

            signal = self._engine.parse_alert(content)
            if signal:
                await self._on_signal(signal)

    async def start(self) -> None:
        token = self._config.discord_bot_token
        if not token:
            raise RuntimeError("DISCORD_BOT_TOKEN is required")
        await self._client.start(token)

    async def close(self) -> None:
        await self._client.close()
