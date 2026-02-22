from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord

from src.config import BotConfig
from src.hyperliquid.client import AccountState
from src.hyperliquid.trader import TradeResult
from src.signals.engine import Signal

logger = logging.getLogger("trading_bot")

MODE_LABELS = {"paper": "PAPER", "testnet": "TESTNET", "mainnet": "LIVE"}


class DiscordNotifier:
    """Sends trade notifications and status updates to a Discord channel."""

    def __init__(self, client: discord.Client, config: BotConfig):
        self._client = client
        self._channel_id = config.discord_notify_channel_id
        self._mode = config.mode
        self._mode_label = MODE_LABELS.get(config.mode, config.mode.upper())

    async def _get_channel(self) -> discord.TextChannel | None:
        channel = self._client.get_channel(self._channel_id)
        if not channel:
            logger.warning("Notify channel %d not found", self._channel_id)
        return channel

    async def send_trade_opened(self, signal: Signal, result: TradeResult) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        color = 0x00FF88 if result.side == "long" else 0xFF4444
        side_emoji = "LONG" if result.side == "long" else "SHORT"

        embed = discord.Embed(
            title=f"{side_emoji} | {result.coin}",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Price", value=f"${result.price:,.2f}", inline=True)
        embed.add_field(name="Size", value=f"{result.size:.6f}", inline=True)
        embed.add_field(name="Confidence", value=f"{signal.confidence:.0%}", inline=True)
        embed.add_field(name="Source", value=signal.source, inline=True)
        embed.add_field(name="Mode", value=self._mode_label, inline=True)
        embed.set_footer(text=f"Smart Money Trading Bot | {self._mode_label}")

        try:
            await channel.send(embed=embed)
            logger.info("Discord notification sent to #%s", channel.name)
        except Exception:
            logger.exception("Failed to send Discord notification")

    async def send_trade_failed(self, coin: str, error: str) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        embed = discord.Embed(
            title=f"TRADE FAILED | {coin}",
            description=error,
            color=0xFF0000,
            timestamp=datetime.now(timezone.utc),
        )
        await channel.send(embed=embed)

    async def send_position_closed(self, result: TradeResult) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        embed = discord.Embed(
            title=f"CLOSED | {result.coin}",
            color=0x888888,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Side", value=result.side, inline=True)
        embed.add_field(name="Price", value=f"${result.price:,.2f}", inline=True)
        await channel.send(embed=embed)

    async def send_status(self, state: AccountState) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        embed = discord.Embed(
            title="Bot Status",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Equity", value=f"${state.equity:,.2f}", inline=True)
        embed.add_field(name="Available", value=f"${state.available_balance:,.2f}", inline=True)
        embed.add_field(name="Positions", value=str(len(state.positions)), inline=True)

        for pos in state.positions:
            pnl_sign = "+" if pos.unrealized_pnl >= 0 else ""
            embed.add_field(
                name=f"{pos.side.upper()} {pos.coin}",
                value=f"Entry: ${pos.entry_price:,.2f}\nPnL: {pnl_sign}${pos.unrealized_pnl:,.2f}",
                inline=True,
            )

        await channel.send(embed=embed)

    async def send_paper_summary(self, summary: dict) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        pnl = summary["total_pnl"]
        ret = summary["return_pct"]
        color = 0x00FF88 if pnl >= 0 else 0xFF4444
        pnl_sign = "+" if pnl >= 0 else ""
        ret_sign = "+" if ret >= 0 else ""

        embed = discord.Embed(
            title="PAPER TRADE Summary",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Equity", value=f"${summary['equity']:,.2f}", inline=True)
        embed.add_field(name="Cash", value=f"${summary['cash']:,.2f}", inline=True)
        embed.add_field(name="Total PnL", value=f"{pnl_sign}${pnl:,.2f}", inline=True)
        embed.add_field(name="Return", value=f"{ret_sign}{ret:.1f}%", inline=True)
        embed.add_field(name="Open Pos.", value=str(summary["open_positions"]), inline=True)
        embed.add_field(name="Closed Trades", value=str(summary["total_trades"]), inline=True)

        for pos in summary.get("positions", []):
            pnl_s = "+" if pos.unrealized_pnl >= 0 else ""
            embed.add_field(
                name=f"{pos.side.upper()} {pos.coin}",
                value=f"Entry: ${pos.entry_price:,.2f}\nPnL: {pnl_s}${pos.unrealized_pnl:,.2f}",
                inline=True,
            )

        embed.set_footer(text="Smart Money Trading Bot | PAPER")
        await channel.send(embed=embed)

    async def send_paper_sl_tp(self, coin: str, side: str, reason: str, pnl: float) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        color = 0x00FF88 if pnl >= 0 else 0xFF4444
        pnl_sign = "+" if pnl >= 0 else ""

        embed = discord.Embed(
            title=f"{reason} | {side.upper()} {coin}",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="PnL", value=f"{pnl_sign}${pnl:,.2f}", inline=True)
        embed.set_footer(text="Smart Money Trading Bot | PAPER")
        await channel.send(embed=embed)

    async def send_agent_analysis(self, signal: Signal, decision) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        color = 0x00FF88 if decision.should_execute else 0xFF4444
        status = "EXECUTE" if decision.should_execute else "SKIP"

        embed = discord.Embed(
            title=f"AI Analysis | {signal.side.upper()} {signal.coin} → {status}",
            description=decision.reasoning[:300],
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="Confidence",
            value=f"{signal.confidence:.0%} → {decision.adjusted_confidence:.0%}",
            inline=True,
        )
        embed.add_field(name="Size Modifier", value=f"{decision.position_size_modifier:.1f}x", inline=True)

        for agent in decision.agent_analyses:
            name = agent.get("_agent", "?")
            rec = agent.get("recommendation", "?")
            conf = agent.get("confidence", 0)
            emoji = {"buy": "BUY", "sell": "SELL", "skip": "SKIP"}.get(rec, rec)
            embed.add_field(name=name, value=f"{emoji} ({conf:.0%})", inline=True)

        if decision.dissenting_views:
            embed.add_field(
                name="Warnings",
                value="\n".join(f"- {v}" for v in decision.dissenting_views[:3]),
                inline=False,
            )

        embed.set_footer(text=f"Smart Money Trading Bot | {self._mode_label}")
        try:
            await channel.send(embed=embed)
        except Exception:
            logger.exception("Failed to send agent analysis")

    async def send_daily_report(
        self, summary: dict, win_rate: dict, closed_trades: list[dict], lessons: list,
    ) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        pnl = summary["total_pnl"]
        ret = summary["return_pct"]
        color = 0x00FF88 if pnl >= 0 else 0xFF4444
        pnl_sign = "+" if pnl >= 0 else ""
        ret_sign = "+" if ret >= 0 else ""

        embed = discord.Embed(
            title="Daily Report",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Equity", value=f"${summary['equity']:,.2f}", inline=True)
        embed.add_field(name="Initial", value=f"${summary['initial_balance']:,.2f}", inline=True)
        embed.add_field(name="Total PnL", value=f"{pnl_sign}${pnl:,.2f}", inline=True)
        embed.add_field(name="Return", value=f"{ret_sign}{ret:.1f}%", inline=True)

        wins = win_rate.get("wins", 0)
        losses = win_rate.get("losses", 0)
        rate = win_rate.get("win_rate", 0)
        embed.add_field(name="Win Rate", value=f"{rate:.0f}% ({wins}W / {losses}L)", inline=True)
        embed.add_field(name="Open Positions", value=str(summary["open_positions"]), inline=True)

        avg_win = win_rate.get("avg_win", 0)
        avg_loss = win_rate.get("avg_loss", 0)
        if avg_win or avg_loss:
            embed.add_field(name="Avg Win", value=f"+${avg_win:,.2f}", inline=True)
            embed.add_field(name="Avg Loss", value=f"-${abs(avg_loss):,.2f}", inline=True)

        today_trades = [t for t in closed_trades[-10:]]
        if today_trades:
            lines = []
            for t in today_trades[-5:]:
                t_pnl = t.get("pnl", 0)
                dot = "+" if t_pnl >= 0 else ""
                lines.append(f"{t['side'].upper()} {t['coin']}: {dot}${t_pnl:,.2f} ({t.get('reason', '')})")
            embed.add_field(name="Recent Trades", value="\n".join(lines), inline=False)

        if lessons:
            embed.add_field(
                name="AI Lessons Learned",
                value="\n".join(f"- {l}" for l in lessons[:3]),
                inline=False,
            )

        embed.set_footer(text=f"Smart Money Trading Bot | {self._mode_label}")
        await channel.send(embed=embed)

    async def send_emergency_halt(self, reason: str) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        embed = discord.Embed(
            title="BOT HALTED",
            description=reason,
            color=0xFF0000,
            timestamp=datetime.now(timezone.utc),
        )
        await channel.send(content="@everyone", embed=embed)

    # ── Interactive command responses ──────────────────────────────

    async def send_cmd_status(self, message: discord.Message, summary: dict) -> None:
        pnl = summary["total_pnl"]
        ret = summary["return_pct"]
        color = 0x00FF88 if pnl >= 0 else 0xFF4444
        pnl_sign = "+" if pnl >= 0 else ""
        ret_sign = "+" if ret >= 0 else ""

        embed = discord.Embed(
            title=f"Bot Status | {self._mode_label}",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Equity", value=f"${summary['equity']:,.2f}", inline=True)
        embed.add_field(name="Cash", value=f"${summary['cash']:,.2f}", inline=True)
        embed.add_field(name="Initial", value=f"${summary['initial_balance']:,.2f}", inline=True)
        embed.add_field(name="Total PnL", value=f"{pnl_sign}${pnl:,.2f}", inline=True)
        embed.add_field(name="Return", value=f"{ret_sign}{ret:.2f}%", inline=True)
        embed.add_field(name="Open Positions", value=str(summary["open_positions"]), inline=True)
        embed.add_field(name="Closed Trades", value=str(summary["total_trades"]), inline=True)
        embed.set_footer(text=f"Smart Money Trading Bot | {self._mode_label}")
        await message.channel.send(embed=embed)

    async def send_cmd_positions(
        self, message: discord.Message, positions: list, coin_prices: dict[str, float],
    ) -> None:
        if not positions:
            embed = discord.Embed(
                title=f"Open Positions | {self._mode_label}",
                description="No open positions.",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text=f"Smart Money Trading Bot | {self._mode_label}")
            await message.channel.send(embed=embed)
            return

        embed = discord.Embed(
            title=f"Open Positions ({len(positions)}) | {self._mode_label}",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )

        for pos in positions:
            current = coin_prices.get(pos.coin, pos.entry_price)
            pnl_sign = "+" if pos.unrealized_pnl >= 0 else ""
            pnl_pct = (pos.unrealized_pnl / (pos.size * pos.entry_price)) * 100 if pos.size * pos.entry_price else 0
            pnl_pct_sign = "+" if pnl_pct >= 0 else ""
            side_label = "LONG" if pos.side == "long" else "SHORT"

            embed.add_field(
                name=f"{side_label} {pos.coin}",
                value=(
                    f"Entry: ${pos.entry_price:,.2f}\n"
                    f"Current: ${current:,.2f}\n"
                    f"Size: {pos.size:.6f}\n"
                    f"PnL: {pnl_sign}${pos.unrealized_pnl:,.2f} ({pnl_pct_sign}{pnl_pct:.1f}%)\n"
                    f"Leverage: {pos.leverage:.0f}x"
                ),
                inline=True,
            )

        embed.set_footer(text=f"Smart Money Trading Bot | {self._mode_label}")
        await message.channel.send(embed=embed)

    async def send_cmd_history(self, message: discord.Message, closed_trades: list[dict]) -> None:
        if not closed_trades:
            embed = discord.Embed(
                title=f"Trade History | {self._mode_label}",
                description="No closed trades yet.",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text=f"Smart Money Trading Bot | {self._mode_label}")
            await message.channel.send(embed=embed)
            return

        last_five = closed_trades[-5:][::-1]

        embed = discord.Embed(
            title=f"Last {len(last_five)} Trades | {self._mode_label}",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )

        for trade in last_five:
            pnl = trade["pnl"]
            pnl_sign = "+" if pnl >= 0 else ""
            color_dot = "🟢" if pnl >= 0 else "🔴"
            side_label = trade["side"].upper()
            closed_at = datetime.fromtimestamp(trade["closed_at"], tz=timezone.utc).strftime("%m/%d %H:%M UTC")

            embed.add_field(
                name=f"{color_dot} {side_label} {trade['coin']}",
                value=(
                    f"Entry: ${trade['entry']:,.2f} → Exit: ${trade['exit']:,.2f}\n"
                    f"Size: {trade['size']:.6f}\n"
                    f"PnL: {pnl_sign}${pnl:,.2f}\n"
                    f"Reason: {trade['reason']}\n"
                    f"Closed: {closed_at}"
                ),
                inline=False,
            )

        embed.set_footer(text=f"Smart Money Trading Bot | {self._mode_label}")
        await message.channel.send(embed=embed)

    async def send_cmd_help(self, message: discord.Message) -> None:
        embed = discord.Embed(
            title=f"Bot Commands | {self._mode_label}",
            description="Available commands for the trading bot:",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="!status", value="Portfolio overview — equity, PnL, return %, open positions", inline=False)
        embed.add_field(name="!positions", value="Details of all open positions with current prices and unrealized PnL", inline=False)
        embed.add_field(name="!history", value="Last 5 closed trades with PnL", inline=False)
        embed.add_field(name="!help", value="Show this help message", inline=False)
        embed.set_footer(text=f"Smart Money Trading Bot | {self._mode_label}")
        await message.channel.send(embed=embed)
