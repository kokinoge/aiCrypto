from __future__ import annotations

import asyncio
import datetime as dt
import logging
import signal
import sys

import discord

from src.agents.adaptive import AdaptiveParams
from src.agents.journal import TradeJournal
from src.agents.researcher import GrokResearcher, create_researcher
from src.agents.rulebook import StrategyRulebook
from src.agents.team import AgentTeam
from src.config import load_config
from src.hyperliquid.client import HyperliquidClient
from src.hyperliquid.paper_trader import PaperTrader
from src.hyperliquid.risk import RiskManager
from src.hyperliquid.trader import Trader
from src.notifications.discord_notifier import DiscordNotifier
from src.signals.discord_monitor import NansenDiscordMonitor
from src.signals.engine import Signal, SignalEngine
from src.coin_lists import CoinListManager
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
        self._adaptive = AdaptiveParams(self._journal, self._config.risk, self._config.signals)
        self._rulebook = StrategyRulebook()
        self._researcher = create_researcher(self._config.xai_api_key)

        self._signal_engine = SignalEngine()
        self._notifier: DiscordNotifier | None = None
        self._monitor: NansenDiscordMonitor | None = None
        self._coin_lists = CoinListManager(
            on_change=self._broadcast_blacklist_change,
        )
        self._webhook: WebhookServer | None = None
        self._status_task: asyncio.Task | None = None
        self._sl_tp_task: asyncio.Task | None = None
        self._daily_task: asyncio.Task | None = None
        self._weekly_task: asyncio.Task | None = None

    async def _broadcast_blacklist_change(self) -> None:
        if self._webhook:
            await self._webhook.broadcast("blacklist_updated", {
                "blacklist": self._coin_lists.get_blacklist(),
            })

    def _get_all_coins_data(self) -> list[dict]:
        """Get all coins with market data for the /api/coins endpoint."""
        try:
            markets = self._hl_client.get_all_coins_with_market_data()
        except Exception:
            logger.exception("Failed to fetch all coins market data")
            return []

        coin_stats = {}
        if hasattr(self, "_journal"):
            try:
                coin_stats = self._journal.get_coin_stats()
            except Exception:
                pass

        coin_adjustments = {}
        if hasattr(self, "_adaptive"):
            try:
                coin_adjustments = self._adaptive.get_overrides().coin_confidence_adjustments
            except Exception:
                pass

        result = []
        for m in markets:
            stats = coin_stats.get(m.coin, {})
            result.append({
                "coin": m.coin,
                "mark_price": m.mark_price,
                "funding_rate": m.funding_rate,
                "open_interest": m.open_interest,
                "trade_count": stats.get("total", 0),
                "win_rate": stats.get("win_rate", None),
                "total_pnl": stats.get("total_pnl", None),
                "confidence_adjustment": coin_adjustments.get(m.coin, 0.0),
            })
        return result

    async def _handle_signal(self, sig: Signal) -> None:
        logger.info("Processing signal: %s %s (confidence=%.2f)", sig.side, sig.coin, sig.confidence)

        # Check blacklist before any processing
        if self._coin_lists.is_blacklisted(sig.coin):
            logger.info("Signal for %s blocked by blacklist", sig.coin)
            return

        # --- Adaptive: skip hours check ---
        should_skip, skip_reason = self._adaptive.should_skip_now()
        if should_skip:
            logger.info("[Adaptive] Skipping: %s", skip_reason)
            return

        # --- Adaptive: adjust confidence ---
        adjusted_conf = self._adaptive.get_adjusted_confidence(sig.coin, sig.confidence)
        if adjusted_conf != sig.confidence:
            logger.info("[Adaptive] Confidence adjusted: %.2f → %.2f for %s", sig.confidence, adjusted_conf, sig.coin)
            sig = Signal(coin=sig.coin, side=sig.side, confidence=adjusted_conf, source=sig.source, raw_message=sig.raw_message)

        # --- Rulebook: check rules ---
        try:
            market_info = self._hl_client.get_market_info(sig.coin)
        except Exception:
            market_info = None

        rule_matches = self._rulebook.check_signal(sig, market_info)
        for match in rule_matches:
            if match.action == "skip":
                logger.info("[Rulebook] Rule triggered — skip: %s", match.reason)
                return
            elif match.action == "reduce_confidence":
                old_conf = sig.confidence
                new_conf = max(0.0, sig.confidence - match.value)
                sig = Signal(coin=sig.coin, side=sig.side, confidence=new_conf, source=sig.source, raw_message=sig.raw_message)
                logger.info("[Rulebook] Confidence reduced: %.2f → %.2f (%s)", old_conf, new_conf, match.reason)

        if sig.confidence < self._config.signals.min_confidence:
            logger.info("Signal confidence %.2f below threshold after adjustments, skipping", sig.confidence)
            return

        # --- Grok Research: real-time sentiment & validation ---
        if self._researcher:
            try:
                validation = await self._researcher.validate_trade_idea(
                    coin=sig.coin, side=sig.side,
                    signal_source=sig.source, confidence=sig.confidence,
                )
                if validation:
                    old_conf = sig.confidence
                    new_conf = max(0.1, min(1.0, sig.confidence + validation.confidence_adjustment))
                    logger.info(
                        "[Grok] %s %s: sentiment=%s | adj=%.2f | %s",
                        sig.side.upper(), sig.coin, validation.twitter_sentiment,
                        validation.confidence_adjustment, validation.reasoning[:80],
                    )
                    if validation.confidence_adjustment != 0:
                        sig = Signal(coin=sig.coin, side=sig.side, confidence=new_conf, source=sig.source, raw_message=sig.raw_message)
                        logger.info("[Grok] Confidence: %.2f → %.2f", old_conf, new_conf)

                    if self._notifier and validation.warnings:
                        try:
                            embed = discord.Embed(
                                title=f"Grokリサーチ | {sig.side.upper()} {sig.coin}",
                                description=validation.reasoning[:300],
                                color=0x1DA1F2,
                            )
                            embed.add_field(name="X/Twitterセンチメント", value=validation.twitter_sentiment, inline=True)
                            embed.add_field(name="信頼度調整", value=f"{validation.confidence_adjustment:+.2f}", inline=True)
                            if validation.warnings:
                                embed.add_field(name="警告", value="\n".join(f"- {w}" for w in validation.warnings[:3]), inline=False)
                            channel = self._notifier._client.get_channel(self._config.discord_notify_channel_id)
                            if channel:
                                await channel.send(embed=embed)
                        except Exception:
                            logger.exception("Error sending Grok research notification")
            except Exception:
                logger.exception("Grok research failed, continuing without it")

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

        # --- Adaptive: apply position size modifier ---
        overrides = self._adaptive.get_overrides()

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

        if result.success and self._webhook:
            await self._webhook.broadcast("trade_executed", {
                "coin": result.coin, "side": result.side,
                "size": result.size, "price": result.price,
            })
            await self._webhook.broadcast("dashboard_update", self._get_dashboard_data())

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
        jst = dt.timezone(dt.timedelta(hours=9))
        while True:
            now_jst = dt.datetime.now(dt.timezone.utc).astimezone(jst)
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

    async def _weekly_review_loop(self) -> None:
        """Run weekly AI review every Sunday at 21:00 JST."""
        jst = dt.timezone(dt.timedelta(hours=9))
        while True:
            now_jst = dt.datetime.now(dt.timezone.utc).astimezone(jst)
            days_until_sunday = (6 - now_jst.weekday()) % 7
            if days_until_sunday == 0 and now_jst.hour >= 21:
                days_until_sunday = 7
            target = now_jst.replace(hour=21, minute=0, second=0, microsecond=0) + dt.timedelta(days=days_until_sunday)
            wait_seconds = (target - now_jst).total_seconds()
            logger.info("Next weekly review in %.1f days", wait_seconds / 86400)
            await asyncio.sleep(wait_seconds)

            try:
                await self._run_weekly_review()
            except Exception:
                logger.exception("Error in weekly review")

    async def _run_weekly_review(self) -> None:
        logger.info("[WeeklyReview] Starting weekly performance review...")

        trades = self._journal.get_past_trades(limit=50)
        win_rate = self._journal.get_win_rate()
        coin_stats = self._journal.get_coin_stats()
        hourly_stats = self._journal.get_hourly_stats()
        agent_accuracy = self._journal.get_agent_accuracy()
        active_rules = self._rulebook.get_active_rules()
        lessons = self._journal.get_lessons(limit=10)

        current_params = {
            "risk_per_trade_pct": self._config.risk.max_risk_per_trade_pct,
            "min_confidence": self._config.signals.min_confidence,
            "position_size_modifier": self._adaptive.get_overrides().position_size_modifier,
        }
        rules_data = [{"description": r.description, "condition_type": r.condition_type, "active": r.active} for r in active_rules]

        review = await self._agent_team.run_weekly_review(
            trades=trades,
            win_rate=win_rate,
            coin_stats=coin_stats,
            hourly_stats=hourly_stats,
            agent_accuracy=agent_accuracy,
            current_rules=rules_data,
            current_params=current_params,
            lessons=[l if isinstance(l, dict) else {"lesson": l} for l in lessons],
        )

        if not review:
            logger.warning("[WeeklyReview] No review data returned")
            return

        # Apply proposed rules
        proposed_rules = review.get("proposed_rules", [])
        for rule_data in proposed_rules[:5]:
            try:
                from src.agents.rulebook import StrategyRule
                rule = StrategyRule(
                    id=f"weekly_{dt.datetime.now().strftime('%Y%m%d')}_{len(self._rulebook.get_active_rules())}",
                    description=rule_data.get("description", ""),
                    condition_type=rule_data.get("condition_type", "custom"),
                    condition=rule_data.get("condition", {}),
                    action=rule_data.get("action", "reduce_confidence"),
                    action_value=rule_data.get("action_value", 0.1),
                    created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                    source="weekly_review",
                )
                self._rulebook.add_rule(rule)
                logger.info("[WeeklyReview] New rule added: %s", rule.description)
            except Exception:
                logger.exception("Failed to add proposed rule")

        if self._notifier:
            try:
                await self._notifier.send_weekly_report(
                    review, win_rate, agent_accuracy, len(active_rules),
                )
            except Exception:
                logger.exception("Error sending weekly report")

        logger.info("[WeeklyReview] Review complete")

    async def _check_sl_tp_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            if not self._config.is_paper:
                continue
            try:
                closed = self._paper_trader.check_sl_tp()
                for pos, reason, pnl in closed:
                    if self._notifier:
                        await self._notifier.send_paper_sl_tp(pos.coin, pos.side, reason, pnl)

                    if self._webhook:
                        await self._webhook.broadcast("position_closed", {
                            "coin": pos.coin, "side": pos.side, "pnl": pnl,
                        })
                        await self._webhook.broadcast("dashboard_update", self._get_dashboard_data())

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
                    if review:
                        if review.get("lessons"):
                            logger.info("[AgentTeam] Lessons: %s", review["lessons"])
                        rule = self._rulebook.add_rule_from_ai(review)
                        if rule:
                            logger.info("[Rulebook] New rule from review: %s", rule.description)

                    self._adaptive.recalculate()
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

    def _get_dashboard_data(self) -> dict:
        summary = self._get_summary()
        win_rate = self._journal.get_win_rate()
        closed = self._get_closed_trades()
        active_rules = self._rulebook.get_active_rules()
        streak = self._journal.get_streak()
        overrides = self._adaptive.get_overrides()
        agent_accuracy = self._journal.get_agent_accuracy()
        lessons = self._journal.get_lessons(limit=5)

        positions_data = []
        for pos in summary.get("positions", []):
            try:
                market = self._hl_client.get_market_info(pos.coin)
                current_price = market.mark_price
            except Exception:
                current_price = pos.entry_price
            positions_data.append({
                "coin": pos.coin, "side": pos.side,
                "entry_price": pos.entry_price,
                "current_price": current_price,
                "size": pos.size,
                "unrealized_pnl": pos.unrealized_pnl,
                "leverage": pos.leverage,
            })

        rules_data = []
        for r in active_rules:
            rules_data.append({
                "id": r.id, "description": r.description,
                "type": r.condition_type, "action": r.action,
                "triggered": r.times_triggered, "correct": r.times_correct,
                "source": r.source,
            })

        coin_stats = self._journal.get_coin_stats(min_trades=1)
        coin_adjustments = overrides.coin_confidence_adjustments

        config_info = {
            "mode": self._config.mode,
            "paper_balance": self._config.paper_trading_balance,
            "risk_per_trade": self._config.risk.max_risk_per_trade_pct,
            "stop_loss": self._config.risk.stop_loss_pct,
            "take_profit": self._config.risk.take_profit_pct,
            "max_positions": self._config.risk.max_positions,
            "max_drawdown": self._config.risk.max_drawdown_pct,
            "max_leverage": self._config.risk.max_leverage,
            "min_confidence": self._config.signals.min_confidence,
            "cooldown_minutes": self._config.signals.cooldown_minutes,
            "trading_pairs": self._config.trading_pairs,
            "grok_enabled": self._researcher is not None,
            "anthropic_enabled": bool(self._config.anthropic_api_key),
            "adaptive_risk": overrides.risk_per_trade_pct,
            "adaptive_confidence": overrides.min_confidence,
            "skip_hours": overrides.skip_hours_utc,
        }

        return {
            "status": "running",
            "mode": self._config.mode,
            "equity": summary["equity"],
            "cash": summary["cash"],
            "initial_balance": summary["initial_balance"],
            "total_pnl": summary["total_pnl"],
            "return_pct": summary["return_pct"],
            "open_positions": positions_data,
            "closed_trades": closed[-20:],
            "win_rate": win_rate,
            "active_rules": len(active_rules),
            "streak": list(streak),
            "position_size_modifier": overrides.position_size_modifier,
            "lessons": [l.get("lesson", str(l)) if isinstance(l, dict) else str(l) for l in lessons],
            "agent_accuracy": agent_accuracy,
            "rules": rules_data,
            "coin_stats": coin_stats,
            "coin_adjustments": coin_adjustments,
            "config": config_info,
        }

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

        elif cmd == "!rules":
            rules = self._rulebook.get_active_rules()
            overrides = self._adaptive.get_overrides()
            streak_type, streak_count = self._journal.get_streak()
            embed = discord.Embed(
                title="学習状況",
                color=0x5865F2,
            )
            embed.add_field(name="アクティブルール", value=str(len(rules)), inline=True)
            embed.add_field(name="連続成績", value=f"{streak_type} {streak_count}回", inline=True)
            embed.add_field(name="サイズ倍率", value=f"{overrides.position_size_modifier:.1f}x", inline=True)
            if overrides.risk_per_trade_pct:
                embed.add_field(name="リスク/取引", value=f"{overrides.risk_per_trade_pct:.1f}%", inline=True)
            if overrides.coin_confidence_adjustments:
                adj_text = "\n".join(f"{c}: {v:+.2f}" for c, v in overrides.coin_confidence_adjustments.items())
                embed.add_field(name="コイン別調整", value=adj_text, inline=False)
            if rules:
                rule_text = "\n".join(f"- {r.description[:50]}" for r in rules[:5])
                embed.add_field(name="ルール一覧", value=rule_text, inline=False)
            await message.channel.send(embed=embed)

        elif cmd == "!help":
            await self._notifier.send_cmd_help(message)

        else:
            embed = discord.Embed(
                description=f"不明なコマンド: `{cmd}`\n`!help` で一覧を表示",
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
        logger.info("ENV CHECK: XAI_API_KEY=%s", "SET" if self._config.xai_api_key else "MISSING")
        logger.info("Grok Researcher: %s", "ENABLED" if self._researcher else "DISABLED")

        overrides = self._adaptive.get_overrides()
        active_rules = self._rulebook.get_active_rules()
        logger.info("Learning: %d active rules | size_mod=%.1fx", len(active_rules), overrides.position_size_modifier)
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
                get_dashboard_data=self._get_dashboard_data,
                get_all_coins_data=self._get_all_coins_data,
                coin_list_manager=self._coin_lists,
            )
            await self._webhook.start()

        self._status_task = asyncio.create_task(self._periodic_status())
        self._daily_task = asyncio.create_task(self._daily_report_loop())
        self._weekly_task = asyncio.create_task(self._weekly_review_loop())
        if self._config.is_paper:
            self._sl_tp_task = asyncio.create_task(self._check_sl_tp_loop())

        logger.info("Starting Discord monitor...")
        await self._monitor.start()

    async def stop(self) -> None:
        logger.info("Shutting down bot...")
        for task in [self._status_task, self._daily_task, self._weekly_task, self._sl_tp_task]:
            if task:
                task.cancel()
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
