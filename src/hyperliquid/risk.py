from __future__ import annotations

import logging
from dataclasses import dataclass

from src.config import BotConfig, RiskConfig
from src.hyperliquid.client import AccountState, HyperliquidClient

logger = logging.getLogger("trading_bot")


@dataclass
class TradeParams:
    coin: str
    side: str  # "long" or "short"
    size: float
    entry_price: float
    stop_loss: float
    take_profit: float
    leverage: int


class RiskManager:
    """Enforces position sizing, drawdown limits, and trade constraints."""

    def __init__(self, config: BotConfig, client: HyperliquidClient):
        self._risk: RiskConfig = config.risk
        self._client = client
        self._initial_equity: float | None = None
        self._halted = False

    @property
    def is_halted(self) -> bool:
        return self._halted

    def initialize(self) -> None:
        state = self._client.get_account_state()
        self._initial_equity = state.equity
        logger.info(
            "RiskManager initialized | equity=%.2f | max_dd=%.1f%%",
            state.equity, self._risk.max_drawdown_pct,
        )

    def check_drawdown(self, current_equity: float) -> bool:
        if self._initial_equity is None:
            return False
        dd_pct = ((self._initial_equity - current_equity) / self._initial_equity) * 100
        if dd_pct >= self._risk.max_drawdown_pct:
            logger.critical(
                "MAX DRAWDOWN REACHED: %.1f%% (limit %.1f%%) — halting bot",
                dd_pct, self._risk.max_drawdown_pct,
            )
            self._halted = True
            return True
        return False

    def can_open_trade(self, state: AccountState) -> tuple[bool, str]:
        if self._halted:
            return False, "Bot is halted due to max drawdown"

        if len(state.positions) >= self._risk.max_positions:
            return False, f"Max positions reached ({self._risk.max_positions})"

        if self.check_drawdown(state.equity):
            return False, "Max drawdown exceeded"

        return True, "OK"

    def calculate_trade_params(
        self, coin: str, side: str, entry_price: float, equity: float
    ) -> TradeParams:
        risk_amount = equity * (self._risk.max_risk_per_trade_pct / 100)
        sl_distance = entry_price * (self._risk.stop_loss_pct / 100)

        size = risk_amount / sl_distance
        size = round(size, 6)

        leverage = min(self._risk.max_leverage, 3)

        if side == "long":
            stop_loss = entry_price * (1 - self._risk.stop_loss_pct / 100)
            take_profit = entry_price * (1 + self._risk.take_profit_pct / 100)
        else:
            stop_loss = entry_price * (1 + self._risk.stop_loss_pct / 100)
            take_profit = entry_price * (1 - self._risk.take_profit_pct / 100)

        return TradeParams(
            coin=coin,
            side=side,
            size=size,
            entry_price=entry_price,
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
            leverage=leverage,
        )
