from __future__ import annotations

import logging
from datetime import datetime, timezone

import discord

from src.config import BotConfig
from src.hyperliquid.client import AccountState
from src.hyperliquid.trader import TradeResult
from src.signals.engine import Signal

logger = logging.getLogger("trading_bot")

MODE_LABELS = {"paper": "模擬取引", "testnet": "テストネット", "mainnet": "本番"}


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
        side_jp = "ロング（買い）" if result.side == "long" else "ショート（売り）"

        embed = discord.Embed(
            title=f"{side_jp} | {result.coin}",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="価格", value=f"${result.price:,.2f}", inline=True)
        embed.add_field(name="数量", value=f"{result.size:.6f}", inline=True)
        embed.add_field(name="信頼度", value=f"{signal.confidence:.0%}", inline=True)
        embed.add_field(name="ソース", value=signal.source, inline=True)
        embed.add_field(name="モード", value=self._mode_label, inline=True)
        embed.set_footer(text=f"Smart Money Bot | {self._mode_label}")

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
            title=f"取引失敗 | {coin}",
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
            title=f"決済 | {result.coin}",
            color=0x888888,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="方向", value=result.side, inline=True)
        embed.add_field(name="価格", value=f"${result.price:,.2f}", inline=True)
        await channel.send(embed=embed)

    async def send_status(self, state: AccountState) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        embed = discord.Embed(
            title="Bot状況",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="資産", value=f"${state.equity:,.2f}", inline=True)
        embed.add_field(name="利用可能", value=f"${state.available_balance:,.2f}", inline=True)
        embed.add_field(name="ポジション数", value=str(len(state.positions)), inline=True)

        for pos in state.positions:
            pnl_sign = "+" if pos.unrealized_pnl >= 0 else ""
            side_jp = "ロング" if pos.side == "long" else "ショート"
            embed.add_field(
                name=f"{side_jp} {pos.coin}",
                value=f"参入: ${pos.entry_price:,.2f}\n損益: {pnl_sign}${pos.unrealized_pnl:,.2f}",
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
            title="模擬取引サマリー",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="資産", value=f"${summary['equity']:,.2f}", inline=True)
        embed.add_field(name="現金", value=f"${summary['cash']:,.2f}", inline=True)
        embed.add_field(name="総損益", value=f"{pnl_sign}${pnl:,.2f}", inline=True)
        embed.add_field(name="リターン", value=f"{ret_sign}{ret:.1f}%", inline=True)
        embed.add_field(name="ポジション数", value=str(summary["open_positions"]), inline=True)
        embed.add_field(name="決済済み", value=str(summary["total_trades"]), inline=True)

        for pos in summary.get("positions", []):
            pnl_s = "+" if pos.unrealized_pnl >= 0 else ""
            side_jp = "ロング" if pos.side == "long" else "ショート"
            embed.add_field(
                name=f"{side_jp} {pos.coin}",
                value=f"参入: ${pos.entry_price:,.2f}\n損益: {pnl_s}${pos.unrealized_pnl:,.2f}",
                inline=True,
            )

        embed.set_footer(text=f"Smart Money Bot | {self._mode_label}")
        await channel.send(embed=embed)

    async def send_paper_sl_tp(self, coin: str, side: str, reason: str, pnl: float) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        color = 0x00FF88 if pnl >= 0 else 0xFF4444
        pnl_sign = "+" if pnl >= 0 else ""
        reason_jp = {"STOP LOSS": "損切り", "TAKE PROFIT": "利確"}.get(reason, reason)
        side_jp = "ロング" if side == "long" else "ショート"

        embed = discord.Embed(
            title=f"{reason_jp} | {side_jp} {coin}",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="損益", value=f"{pnl_sign}${pnl:,.2f}", inline=True)
        embed.set_footer(text=f"Smart Money Bot | {self._mode_label}")
        await channel.send(embed=embed)

    async def send_agent_analysis(self, signal: Signal, decision) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        color = 0x00FF88 if decision.should_execute else 0xFF4444
        status = "実行" if decision.should_execute else "見送り"
        side_jp = "ロング" if signal.side == "long" else "ショート"

        embed = discord.Embed(
            title=f"AI分析 | {side_jp} {signal.coin} → {status}",
            description=decision.reasoning[:300],
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="信頼度",
            value=f"{signal.confidence:.0%} → {decision.adjusted_confidence:.0%}",
            inline=True,
        )
        embed.add_field(name="サイズ倍率", value=f"{decision.position_size_modifier:.1f}x", inline=True)

        agent_names_jp = {
            "MarketAnalyst": "市場分析",
            "SignalValidator": "シグナル検証",
            "RiskManager": "リスク管理",
            "Contrarian": "反対意見",
        }
        rec_jp = {"buy": "買い", "sell": "売り", "skip": "見送り"}

        for agent in decision.agent_analyses:
            name = agent.get("_agent", "?")
            name_jp = agent_names_jp.get(name, name)
            rec = agent.get("recommendation", "?")
            conf = agent.get("confidence", 0)
            rec_label = rec_jp.get(rec, rec)
            embed.add_field(name=name_jp, value=f"{rec_label} ({conf:.0%})", inline=True)

        if decision.dissenting_views:
            embed.add_field(
                name="警告",
                value="\n".join(f"- {v}" for v in decision.dissenting_views[:3]),
                inline=False,
            )

        embed.set_footer(text=f"Smart Money Bot | {self._mode_label}")
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
            title="日次レポート",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="資産", value=f"${summary['equity']:,.2f}", inline=True)
        embed.add_field(name="初期資金", value=f"${summary['initial_balance']:,.2f}", inline=True)
        embed.add_field(name="総損益", value=f"{pnl_sign}${pnl:,.2f}", inline=True)
        embed.add_field(name="リターン", value=f"{ret_sign}{ret:.1f}%", inline=True)

        wins = win_rate.get("wins", 0)
        losses = win_rate.get("losses", 0)
        rate = win_rate.get("win_rate", 0)
        embed.add_field(name="勝率", value=f"{rate:.0f}% ({wins}勝 / {losses}敗)", inline=True)
        embed.add_field(name="ポジション数", value=str(summary["open_positions"]), inline=True)

        avg_win = win_rate.get("avg_win", 0)
        avg_loss = win_rate.get("avg_loss", 0)
        if avg_win or avg_loss:
            embed.add_field(name="平均利益", value=f"+${avg_win:,.2f}", inline=True)
            embed.add_field(name="平均損失", value=f"-${abs(avg_loss):,.2f}", inline=True)

        if closed_trades:
            lines = []
            side_jp = {"long": "ロング", "short": "ショート"}
            reason_jp = {"STOP LOSS": "損切り", "TAKE PROFIT": "利確", "EMERGENCY CLOSE": "緊急決済"}
            for t in closed_trades[-5:]:
                t_pnl = t.get("pnl", 0)
                dot = "+" if t_pnl >= 0 else ""
                s = side_jp.get(t["side"], t["side"])
                r = reason_jp.get(t.get("reason", ""), t.get("reason", ""))
                lines.append(f"{s} {t['coin']}: {dot}${t_pnl:,.2f} ({r})")
            embed.add_field(name="最近の取引", value="\n".join(lines), inline=False)

        if lessons:
            embed.add_field(
                name="AIの学び",
                value="\n".join(f"- {l}" for l in lessons[:3]),
                inline=False,
            )

        embed.set_footer(text=f"Smart Money Bot | {self._mode_label}")
        await channel.send(embed=embed)

    async def send_emergency_halt(self, reason: str) -> None:
        channel = await self._get_channel()
        if not channel:
            return

        embed = discord.Embed(
            title="Bot緊急停止",
            description=reason,
            color=0xFF0000,
            timestamp=datetime.now(timezone.utc),
        )
        await channel.send(content="@everyone", embed=embed)

    # ── コマンド応答 ──────────────────────────────────

    async def send_cmd_status(self, message: discord.Message, summary: dict) -> None:
        pnl = summary["total_pnl"]
        ret = summary["return_pct"]
        color = 0x00FF88 if pnl >= 0 else 0xFF4444
        pnl_sign = "+" if pnl >= 0 else ""
        ret_sign = "+" if ret >= 0 else ""

        embed = discord.Embed(
            title=f"Bot状況 | {self._mode_label}",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="資産", value=f"${summary['equity']:,.2f}", inline=True)
        embed.add_field(name="現金", value=f"${summary['cash']:,.2f}", inline=True)
        embed.add_field(name="初期資金", value=f"${summary['initial_balance']:,.2f}", inline=True)
        embed.add_field(name="総損益", value=f"{pnl_sign}${pnl:,.2f}", inline=True)
        embed.add_field(name="リターン", value=f"{ret_sign}{ret:.2f}%", inline=True)
        embed.add_field(name="ポジション数", value=str(summary["open_positions"]), inline=True)
        embed.add_field(name="決済済み", value=str(summary["total_trades"]), inline=True)
        embed.set_footer(text=f"Smart Money Bot | {self._mode_label}")
        await message.channel.send(embed=embed)

    async def send_cmd_positions(
        self, message: discord.Message, positions: list, coin_prices: dict[str, float],
    ) -> None:
        if not positions:
            embed = discord.Embed(
                title=f"ポジション一覧 | {self._mode_label}",
                description="現在オープンポジションはありません。",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text=f"Smart Money Bot | {self._mode_label}")
            await message.channel.send(embed=embed)
            return

        embed = discord.Embed(
            title=f"ポジション一覧 ({len(positions)}件) | {self._mode_label}",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )

        for pos in positions:
            current = coin_prices.get(pos.coin, pos.entry_price)
            pnl_sign = "+" if pos.unrealized_pnl >= 0 else ""
            pnl_pct = (pos.unrealized_pnl / (pos.size * pos.entry_price)) * 100 if pos.size * pos.entry_price else 0
            pnl_pct_sign = "+" if pnl_pct >= 0 else ""
            side_jp = "ロング" if pos.side == "long" else "ショート"

            embed.add_field(
                name=f"{side_jp} {pos.coin}",
                value=(
                    f"参入: ${pos.entry_price:,.2f}\n"
                    f"現在: ${current:,.2f}\n"
                    f"数量: {pos.size:.6f}\n"
                    f"損益: {pnl_sign}${pos.unrealized_pnl:,.2f} ({pnl_pct_sign}{pnl_pct:.1f}%)\n"
                    f"レバレッジ: {pos.leverage:.0f}x"
                ),
                inline=True,
            )

        embed.set_footer(text=f"Smart Money Bot | {self._mode_label}")
        await message.channel.send(embed=embed)

    async def send_cmd_history(self, message: discord.Message, closed_trades: list[dict]) -> None:
        if not closed_trades:
            embed = discord.Embed(
                title=f"取引履歴 | {self._mode_label}",
                description="まだ決済済みの取引はありません。",
                color=0x5865F2,
                timestamp=datetime.now(timezone.utc),
            )
            embed.set_footer(text=f"Smart Money Bot | {self._mode_label}")
            await message.channel.send(embed=embed)
            return

        last_five = closed_trades[-5:][::-1]
        side_jp = {"long": "ロング", "short": "ショート"}
        reason_jp = {"STOP LOSS": "損切り", "TAKE PROFIT": "利確", "EMERGENCY CLOSE": "緊急決済"}

        embed = discord.Embed(
            title=f"直近{len(last_five)}件の取引 | {self._mode_label}",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )

        for trade in last_five:
            pnl = trade["pnl"]
            pnl_sign = "+" if pnl >= 0 else ""
            color_dot = "🟢" if pnl >= 0 else "🔴"
            s = side_jp.get(trade["side"], trade["side"].upper())
            r = reason_jp.get(trade.get("reason", ""), trade.get("reason", ""))
            closed_at = datetime.fromtimestamp(trade["closed_at"], tz=timezone.utc).strftime("%m/%d %H:%M UTC")

            embed.add_field(
                name=f"{color_dot} {s} {trade['coin']}",
                value=(
                    f"参入: ${trade['entry']:,.2f} → 決済: ${trade['exit']:,.2f}\n"
                    f"数量: {trade['size']:.6f}\n"
                    f"損益: {pnl_sign}${pnl:,.2f}\n"
                    f"理由: {r}\n"
                    f"日時: {closed_at}"
                ),
                inline=False,
            )

        embed.set_footer(text=f"Smart Money Bot | {self._mode_label}")
        await message.channel.send(embed=embed)

    async def send_cmd_help(self, message: discord.Message) -> None:
        embed = discord.Embed(
            title=f"コマンド一覧 | {self._mode_label}",
            description="利用可能なコマンド:",
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="!status", value="資産状況（残高・損益・リターン・ポジション数）", inline=False)
        embed.add_field(name="!positions", value="オープンポジションの詳細（現在価格・含み損益）", inline=False)
        embed.add_field(name="!history", value="直近5件の決済済み取引", inline=False)
        embed.add_field(name="!help", value="このヘルプを表示", inline=False)
        embed.set_footer(text=f"Smart Money Bot | {self._mode_label}")
        await message.channel.send(embed=embed)
