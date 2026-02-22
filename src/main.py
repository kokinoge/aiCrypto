from __future__ import annotations

import asyncio
import logging
import signal
import sys

import discord

from src.agents.journal import TradeJournal
from src.agents.team import AgentTeam
from src.config import load_config
from src.hyperliquid.client import HyperliquidClient
from src.hyperliquid.paper_trader import PaperTrader
from src.hyperliquid.risk import RiskManager
from src.hyperliquid.trader import Trader
from src.notifications.discord_notifier import DiscordNotifier
from src.signals.discord_monitor import NansenDiscordMonitor
from src.signals.engine import Signal, SignalEngine
from src.signals.webhook_server import WebhookServer
from src.utils.logger import setup_logger

logger = logging.getLogger("trading_bot")


class TradingBot:
    def __init__(self):
        self._config = load_config()
        self._logger = setup_logger(
            level=self._config.logging.level,
            log_file=self._config.logging.file,
        )
        self._hl_client = HyperliquidClient(self._config)
        self._risk_manager = RiskManager(self._config, self._hl_client)

        if self._config.is_paper:
            self._paper_trader = PaperTrader(self._config, self._hl_client, self._risk_manager)
            self._trader: Trader | None = None
        else:
            self._paper_trader = None
            self._trader = Trader(self._config, self._hl_client, self._risk_manager)

        self._journal = TradeJournal()
        self._agent_team = AgentTeam(self._config, self._hl_client, self._risk_manager, self._journal)

        self._signal_engine = SignalEngine()
        self._notifier: DiscordNotifier | None = None
        self._monitor: NansenDiscordMonitor | None = None
        self._webhook: WebhookServer | None = None
        self._status_task: asyncio.Task | None = None
        self._sl_tp_task: asyncio.Task | None = None

    async def _handle_signal(self, sig: Signal) -> None:
        logger.info("Processing signal: %s %s (confidence=%.2f)", sig.side, sig.coin, sig.confidence)

        # --- Agent Team Analysis ---
        account_state = None
        try:
            if self._config.is_paper:
                account_state = self._paper_trader.get_account_state()
            elif self._config.hl_account_address:
                account_state = self._hl_client.get_account_state()
        except Exception:
            logger.warning("Failed to get account state for agent analysis")

        decision = None
        if account_state:
            decision = await self._agent_team.analyze_signal(sig, account_state)
            if decision.agent_analyses:
                logger.info(
                    "[AgentTeam] Decision: execute=%s | confidence=%.2f→%.2f | size_mod=%.1fx | %s",
                    decision.should_execute, sig.confidence,
                    decision.adjusted_confidence, decision.position_size_modifier,
                    decision.reasoning[:100],
                )
                if self._notifier:
                    try:
                        await self._notifier.send_agent_analysis(sig, decision)
                    except Exception:
                        logger.exception("Error sending agent analysis notification")

                if not decision.should_execute:
                    logger.info("Agent team rejected signal for %s — skipping", sig.coin)
                    return

        trade_confidence = decision.adjusted_confidence if decision and decision.agent_analyses else sig.confidence

        try:
            if self._config.is_paper:
                result = self._paper_trader.execute_signal(sig.coin, sig.side, trade_confidence)
            else:
                result = self._trader.execute_signal(sig.coin, sig.side, trade_confidence)
        except Exception:
            logger.exception("Error executing signal for %s", sig.coin)
            return

        if result is None:
            return

        if result.success and self._notifier:
            try:
                await self._notifier.send_trade_opened(sig, result)
            except Exception:
                logger.exception("Error sending trade notification")
        elif not result.success and self._notifier and result.error:
            try:
                await self._notifier.send_trade_failed(result.coin, result.error)
            except Exception:
                logger.exception("Error sending failure notification")

        if not self._config.is_paper and self._risk_manager.is_halted:
            logger.critical("Risk manager halted — closing all positions")
            close_results = self._trader.close_all_positions()
            if self._notifier:
                await self._notifier.send_emergency_halt(
                    f"Max drawdown exceeded. Closed {len(close_results)} positions."
                )

    async def _periodic_status(self) -> None:
        while True:
            await asyncio.sleep(3600)
            try:
                if self._config.is_paper:
                    summary = self._paper_trader.get_summary()
                    logger.info(
                        "[PAPER] Equity=$%.2f | PnL=$%.2f | Return=%.1f%% | Positions=%d",
                        summary["equity"], summary["total_pnl"],
                        summary["return_pct"], summary["open_positions"],
                    )
                    if self._notifier:
                        await self._notifier.send_paper_summary(summary)
                else:
                    state = self._hl_client.get_account_state()
                    self._risk_manager.check_drawdown(state.equity)
                    if self._notifier:
                        await self._notifier.send_status(state)
                    if self._risk_manager.is_halted:
                        self._trader.close_all_positions()
                        if self._notifier:
                            await self._notifier.send_emergency_halt("Max drawdown exceeded")
            except Exception:
                logger.exception("Error in periodic status check")

    async def _daily_report_loop(self) -> None:
        """Send a daily performance report at 9:00 AM JST (00:00 UTC)."""
        import datetime as dt
        while True:
            now = dt.datetime.now(dt.timezone.utc)
            jst = dt.timezone(dt.timedelta(hours=9))
            now_jst = now.astimezone(jst)
            target = now_jst.replace(hour=9, minute=0, second=0, microsecond=0)
            if now_jst >= target:
                target += dt.timedelta(days=1)
            wait_seconds = (target - now_jst).total_seconds()
            logger.info("Next daily report in %.0f hours", wait_seconds / 3600)
            await asyncio.sleep(wait_seconds)

            try:
                if self._notifier:
                    summary = self._get_summary()
                    win_rate = self._journal.get_win_rate()
                    closed = self._get_closed_trades()
                    lessons = self._journal.get_lessons(limit=3)
                    await self._notifier.send_daily_report(summary, win_rate, closed, lessons)
                    logger.info("Daily report sent")
            except Exception:
                logger.exception("Error sending daily report")

    async def _check_sl_tp_loop(self) -> None:
        """Periodically check paper positions for SL/TP hits."""
        while True:
            await asyncio.sleep(60)
            if not self._config.is_paper:
                continue
            try:
                closed = self._paper_trader.check_sl_tp()
                for pos, reason, pnl in closed:
                    if self._notifier:
                        await self._notifier.send_paper_sl_tp(pos.coin, pos.side, reason, pnl)

                    trade_record = {
                        "coin": pos.coin, "side": pos.side,
                        "entry": pos.entry_price, "exit": pos.entry_price,
                        "size": pos.size, "pnl": pnl, "reason": reason,
                    }
                    self._journal.record_trade_result(
                        coin=pos.coin, side=pos.side,
                        entry_price=pos.entry_price, exit_price=pos.entry_price,
                        pnl=pnl, reason=reason,
                    )
                    review = await self._agent_team.review_trade(trade_record)
                    if review and review.get("lessons"):
                        logger.info("[AgentTeam] Lessons: %s", review["lessons"])
            except Exception:
                logger.exception("Error checking SL/TP")

    def _get_summary(self) -> dict:
        if self._config.is_paper:
            return self._paper_trader.get_summary()
        state = self._hl_client.get_account_state()
        return {
            "equity": state.equity,
            "cash": state.available_balance,
            "initial_balance": state.equity,
            "total_pnl": sum(p.unrealized_pnl for p in state.positions),
            "return_pct": 0.0,
            "open_positions": len(state.positions),
            "total_trades": 0,
            "positions": state.positions,
        }

    def _get_closed_trades(self) -> list[dict]:
        if self._config.is_paper:
            return self._paper_trader._portfolio.closed_trades
        return []

    def _get_coin_prices(self, positions) -> dict[str, float]:
        prices: dict[str, float] = {}
        for pos in positions:
            try:
                market = self._hl_client.get_market_info(pos.coin)
                prices[pos.coin] = market.mark_price
            except Exception:
                prices[pos.coin] = pos.entry_price
        return prices

    async def _handle_command(self, cmd: str, message: discord.Message) -> None:
        if not self._notifier:
            return

        if cmd == "!status":
            summary = self._get_summary()
            await self._notifier.send_cmd_status(message, summary)

        elif cmd == "!positions":
            summary = self._get_summary()
            positions = summary["positions"]
            prices = self._get_coin_prices(positions)
            await self._notifier.send_cmd_positions(message, positions, prices)

        elif cmd == "!history":
            closed = self._get_closed_trades()
            await self._notifier.send_cmd_history(message, closed)

        elif cmd == "!help":
            await self._notifier.send_cmd_help(message)

        else:
            embed = discord.Embed(
                description=f"Unknown command: `{cmd}`\nType `!help` for available commands.",
                color=0xFF4444,
            )
            await message.channel.send(embed=embed)

    async def start(self) -> None:
        logger.info("=" * 60)
        logger.info("Smart Money Trading Bot starting...")
        mode_display = {"paper": "PAPER TRADE (模擬取引)", "testnet": "TESTNET", "mainnet": "MAINNET (本番)"}
        logger.info("Mode: %s", mode_display.get(self._config.mode, self._config.mode))
        if self._config.is_paper:
            logger.info("Paper balance: $%.2f", self._config.paper_trading_balance)

        logger.info("ENV CHECK: DISCORD_BOT_TOKEN=%s", "SET" if self._config.discord_bot_token else "MISSING")
        logger.info("ENV CHECK: DISCORD_NANSEN_CHANNEL_ID=%s", self._config.discord_nansen_channel_id or "MISSING")
        logger.info("ENV CHECK: DISCORD_NOTIFY_CHANNEL_ID=%s", self._config.discord_notify_channel_id or "MISSING")
        logger.info("ENV CHECK: HL_ACCOUNT_ADDRESS=%s", "SET" if self._config.hl_account_address else "MISSING")
        logger.info("ENV CHECK: ANTHROPIC_API_KEY=%s", "SET" if self._config.anthropic_api_key else "MISSING")
        logger.info("=" * 60)

        tradeable = self._hl_client.get_tradeable_coins()
        self._signal_engine.update_tradeable_coins(tradeable)
        logger.info("Loaded %d tradeable coins from Hyperliquid", len(tradeable))

        if not self._config.is_paper and self._config.hl_secret_key:
            self._risk_manager.initialize()

        self._monitor = NansenDiscordMonitor(
            config=self._config,
            signal_engine=self._signal_engine,
            on_signal=self._handle_signal,
            on_command=self._handle_command,
        )
        self._notifier = DiscordNotifier(
            client=self._monitor._client,
            config=self._config,
        )

        if self._config.webhook_enabled:
            self._webhook = WebhookServer(
                config=self._config,
                signal_engine=self._signal_engine,
                on_signal=self._handle_signal,
            )
            await self._webhook.start()

        self._status_task = asyncio.create_task(self._periodic_status())
        self._daily_task = asyncio.create_task(self._daily_report_loop())
        if self._config.is_paper:
            self._sl_tp_task = asyncio.create_task(self._check_sl_tp_loop())

        logger.info("Starting Discord monitor...")
        await self._monitor.start()

    async def stop(self) -> None:
        logger.info("Shutting down bot...")
        if self._status_task:
            self._status_task.cancel()
        if hasattr(self, '_daily_task') and self._daily_task:
            self._daily_task.cancel()
        if self._sl_tp_task:
            self._sl_tp_task.cancel()
        if self._webhook:
            await self._webhook.stop()
        if self._monitor:
            await self._monitor.close()
        logger.info("Bot stopped.")


def main() -> None:
    bot = TradingBot()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def shutdown(sig, frame):
        logger.info("Received shutdown signal")
        loop.create_task(bot.stop())
        loop.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(bot.start())
    except KeyboardInterrupt:
        loop.run_until_complete(bot.stop())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
