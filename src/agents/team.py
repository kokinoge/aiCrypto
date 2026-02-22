from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from src.agents.journal import TradeJournal
from src.agents.prompts import (
    CONTRARIAN_SYSTEM_PROMPT,
    MARKET_ANALYST_SYSTEM_PROMPT,
    POST_TRADE_REVIEWER_SYSTEM_PROMPT,
    RISK_MANAGER_SYSTEM_PROMPT,
    SIGNAL_VALIDATOR_SYSTEM_PROMPT,
    STRATEGIST_SYSTEM_PROMPT,
    build_contrarian_prompt,
    build_market_analyst_prompt,
    build_post_trade_reviewer_prompt,
    build_risk_manager_prompt,
    build_signal_validator_prompt,
    build_strategist_prompt,
)
from src.config import BotConfig
from src.hyperliquid.client import AccountState, HyperliquidClient, MarketInfo
from src.hyperliquid.risk import RiskManager
from src.signals.engine import Signal

logger = logging.getLogger("trading_bot")

MODEL = "claude-sonnet-4-20250514"
AGENT_MAX_TOKENS = 500
STRATEGIST_MAX_TOKENS = 800


@dataclass
class TeamDecision:
    should_execute: bool
    adjusted_confidence: float
    position_size_modifier: float
    reasoning: str
    agent_analyses: list[dict] = field(default_factory=list)
    dissenting_views: list[str] = field(default_factory=list)


def _default_decision(signal: Signal) -> TeamDecision:
    return TeamDecision(
        should_execute=True,
        adjusted_confidence=signal.confidence,
        position_size_modifier=1.0,
        reasoning="AI agent team unavailable — proceeding with original signal confidence",
    )


class AgentTeam:
    """Orchestrates a team of AI agents that analyse trading signals in parallel."""

    def __init__(
        self,
        config: BotConfig,
        client: HyperliquidClient,
        risk_manager: RiskManager,
        journal: TradeJournal,
    ) -> None:
        self._config = config
        self._client = client
        self._risk = risk_manager
        self._journal = journal
        self._enabled = bool(config.anthropic_api_key)
        self._warned = False
        self._anthropic = None

        if self._enabled:
            try:
                from anthropic import AsyncAnthropic
                self._anthropic = AsyncAnthropic(api_key=config.anthropic_api_key)
            except ImportError:
                logger.warning("anthropic package not installed — agent team disabled")
                self._enabled = False

    async def analyze_signal(
        self, signal: Signal, account_state: AccountState
    ) -> TeamDecision:
        if not self._enabled:
            self._warn_disabled()
            return _default_decision(signal)

        try:
            market = self._client.get_market_info(signal.coin)
        except Exception:
            logger.warning("Failed to get market info for %s — skipping AI analysis", signal.coin)
            return _default_decision(signal)

        journal_context = self._journal.get_past_trades(limit=10)
        params = self._risk.calculate_trade_params(
            coin=signal.coin, side=signal.side,
            entry_price=market.mark_price, equity=account_state.equity,
        )
        positions_data = [
            {"coin": p.coin, "side": p.side, "entry_price": p.entry_price, "pnl": p.unrealized_pnl}
            for p in account_state.positions
        ]

        try:
            analyst, validator, risk_mgr, contrarian = await asyncio.gather(
                self._run_agent(
                    "MarketAnalyst",
                    MARKET_ANALYST_SYSTEM_PROMPT,
                    build_market_analyst_prompt(
                        coin=signal.coin, side=signal.side,
                        current_price=market.mark_price,
                        price_change_1h=0.0, price_change_24h=0.0,
                        funding_rate=market.funding_rate,
                        open_interest=market.open_interest,
                        volume_24h=0.0,
                        learning_journal=journal_context,
                    ),
                ),
                self._run_agent(
                    "SignalValidator",
                    SIGNAL_VALIDATOR_SYSTEM_PROMPT,
                    build_signal_validator_prompt(
                        coin=signal.coin, side=signal.side,
                        signal_confidence=signal.confidence,
                        raw_message=signal.raw_message,
                        source=signal.source,
                        learning_journal=journal_context,
                    ),
                ),
                self._run_agent(
                    "RiskManager",
                    RISK_MANAGER_SYSTEM_PROMPT,
                    build_risk_manager_prompt(
                        coin=signal.coin, side=signal.side,
                        entry_price=market.mark_price,
                        stop_loss=params.stop_loss, take_profit=params.take_profit,
                        proposed_size=params.size, leverage=params.leverage,
                        equity=account_state.equity,
                        available_balance=account_state.available_balance,
                        open_positions=positions_data,
                        max_risk_per_trade_pct=self._config.risk.max_risk_per_trade_pct,
                        max_positions=self._config.risk.max_positions,
                        max_drawdown_pct=self._config.risk.max_drawdown_pct,
                        learning_journal=journal_context,
                    ),
                ),
                self._run_agent(
                    "Contrarian",
                    CONTRARIAN_SYSTEM_PROMPT,
                    build_contrarian_prompt(
                        coin=signal.coin, side=signal.side,
                        current_price=market.mark_price,
                        price_change_1h=0.0, price_change_24h=0.0,
                        funding_rate=market.funding_rate,
                        open_interest=market.open_interest,
                        volume_24h=0.0,
                        signal_confidence=signal.confidence,
                        open_positions=positions_data,
                        learning_journal=journal_context,
                    ),
                ),
            )
        except Exception:
            logger.exception("Agent team parallel execution failed")
            return _default_decision(signal)

        agent_outputs = [analyst, validator, risk_mgr, contrarian]

        try:
            strategist = await self._run_agent(
                "Strategist",
                STRATEGIST_SYSTEM_PROMPT,
                build_strategist_prompt(
                    coin=signal.coin, side=signal.side,
                    market_analyst_result=analyst,
                    signal_validator_result=validator,
                    risk_manager_result=risk_mgr,
                    contrarian_result=contrarian,
                ),
                max_tokens=STRATEGIST_MAX_TOKENS,
            )
        except Exception:
            logger.exception("Strategist agent failed")
            return _default_decision(signal)

        decision = self._build_decision(signal, strategist, agent_outputs)

        self._journal.record_analysis(
            signal={"coin": signal.coin, "side": signal.side, "confidence": signal.confidence, "source": signal.source},
            agent_analyses={a.get("_agent", "unknown"): a for a in agent_outputs},
            final_decision={"should_execute": decision.should_execute, "confidence": decision.adjusted_confidence, "reasoning": decision.reasoning},
        )

        return decision

    async def review_trade(self, trade_record: dict) -> dict:
        if not self._enabled:
            return {}

        try:
            result = await self._run_agent(
                "PostTradeReviewer",
                POST_TRADE_REVIEWER_SYSTEM_PROMPT,
                build_post_trade_reviewer_prompt(
                    coin=trade_record["coin"],
                    side=trade_record["side"],
                    entry_price=trade_record["entry"],
                    exit_price=trade_record["exit"],
                    size=trade_record["size"],
                    pnl=trade_record["pnl"],
                    exit_reason=trade_record.get("reason", "unknown"),
                    duration_hours=0.0,
                    learning_journal=self._journal.get_past_trades(limit=10),
                ),
                max_tokens=STRATEGIST_MAX_TOKENS,
            )
            self._journal.record_review(trade_record["coin"], result)
            return result
        except Exception:
            logger.exception("Trade review failed")
            return {}

    async def _run_agent(
        self, name: str, system_prompt: str, user_prompt: str, *, max_tokens: int = AGENT_MAX_TOKENS
    ) -> dict:
        logger.debug("Running agent: %s", name)
        response = await self._anthropic.messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = response.content[0].text
        parsed = self._parse_json(raw, name)
        parsed["_agent"] = name
        logger.info("[AgentTeam] %s: %s (conf=%.2f)", name,
                     parsed.get("recommendation", parsed.get("final_decision", "?")),
                     parsed.get("confidence", parsed.get("adjusted_confidence", 0)))
        return parsed

    @staticmethod
    def _parse_json(text: str, agent_name: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        logger.warning("Agent %s returned non-JSON: %s", agent_name, text[:200])
        return {"raw_response": text, "parse_error": True}

    def _build_decision(self, signal: Signal, strategist: dict, agent_outputs: list[dict]) -> TeamDecision:
        final = strategist.get("final_decision", "execute")
        should_execute = final in ("execute", "buy", "sell", True)

        conf = float(strategist.get("adjusted_confidence", signal.confidence))
        conf = max(0.0, min(1.0, conf))

        modifier = float(strategist.get("position_size_modifier", 1.0))
        modifier = max(0.5, min(1.5, modifier))

        reasoning = strategist.get("reasoning", "No reasoning provided")
        dissenting = strategist.get("dissenting_views", [])
        if isinstance(dissenting, str):
            dissenting = [dissenting]

        return TeamDecision(
            should_execute=should_execute,
            adjusted_confidence=conf,
            position_size_modifier=modifier,
            reasoning=reasoning,
            agent_analyses=agent_outputs,
            dissenting_views=dissenting,
        )

    def _warn_disabled(self) -> None:
        if not self._warned:
            logger.warning("ANTHROPIC_API_KEY not set — agent team disabled")
            self._warned = True
