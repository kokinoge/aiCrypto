from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

from src.config import BotConfig
from src.hyperliquid.client import HyperliquidClient
from src.hyperliquid.risk import RiskManager, TradeParams

logger = logging.getLogger("trading_bot")


@dataclass
class TradeResult:
    success: bool
    coin: str
    side: str
    size: float
    price: float
    order_id: str | None = None
    error: str | None = None


class Trader:
    """Executes trades on Hyperliquid with risk management enforcement."""

    def __init__(self, config: BotConfig, client: HyperliquidClient, risk_manager: RiskManager):
        self._config = config
        self._client = client
        self._risk = risk_manager
        self._cooldowns: dict[str, float] = {}

    def _is_on_cooldown(self, coin: str) -> bool:
        last = self._cooldowns.get(coin)
        if last is None:
            return False
        elapsed = (time.time() - last) / 60
        return elapsed < self._config.signals.cooldown_minutes

    def _validate_coin(self, coin: str) -> bool:
        pairs = self._config.trading_pairs
        if pairs and coin not in pairs:
            logger.info("Coin %s not in allowed trading pairs, skipping", coin)
            return False
        return True

    def execute_signal(self, coin: str, side: str, confidence: float) -> TradeResult | None:
        if confidence < self._config.signals.min_confidence:
            logger.debug("Signal confidence %.2f below threshold %.2f for %s", confidence, self._config.signals.min_confidence, coin)
            return None

        if not self._validate_coin(coin):
            return None

        if self._is_on_cooldown(coin):
            logger.info("Coin %s is on cooldown, skipping", coin)
            return None

        state = self._client.get_account_state()

        can_trade, reason = self._risk.can_open_trade(state)
        if not can_trade:
            logger.warning("Trade blocked: %s", reason)
            return TradeResult(success=False, coin=coin, side=side, size=0, price=0, error=reason)

        for pos in state.positions:
            if pos.coin == coin:
                logger.info("Already have position in %s, skipping", coin)
                return None

        market = self._client.get_market_info(coin)
        params = self._risk.calculate_trade_params(
            coin=coin,
            side=side,
            entry_price=market.mark_price,
            equity=state.equity,
        )

        logger.info(
            "Executing trade: %s %s | size=%.6f | entry=%.2f | SL=%.2f | TP=%.2f",
            side.upper(), coin, params.size, params.entry_price,
            params.stop_loss, params.take_profit,
        )

        result = self._place_order(params)

        if result.success:
            self._cooldowns[coin] = time.time()
            self._place_stop_loss(params)
            self._place_take_profit(params)

        return result

    def _place_order(self, params: TradeParams) -> TradeResult:
        try:
            is_buy = params.side == "long"
            order_type = {"limit": {"tif": "Ioc"}}

            slippage = 0.005
            if is_buy:
                limit_price = round(params.entry_price * (1 + slippage), 2)
            else:
                limit_price = round(params.entry_price * (1 - slippage), 2)

            result = self._client.exchange.order(
                coin=params.coin,
                is_buy=is_buy,
                sz=params.size,
                limit_px=limit_price,
                order_type=order_type,
            )

            if result.get("status") == "ok":
                statuses = result["response"]["data"]["statuses"]
                filled = any("filled" in s for s in statuses)
                if filled:
                    fill_info = next(s["filled"] for s in statuses if "filled" in s)
                    logger.info("Order filled: %s %s @ %.2f", params.side, params.coin, float(fill_info.get("avgPx", params.entry_price)))
                    return TradeResult(
                        success=True,
                        coin=params.coin,
                        side=params.side,
                        size=params.size,
                        price=float(fill_info.get("avgPx", params.entry_price)),
                        order_id=str(fill_info.get("oid", "")),
                    )
                else:
                    logger.warning("Order not filled (IOC expired): %s %s", params.side, params.coin)
                    return TradeResult(success=False, coin=params.coin, side=params.side, size=params.size, price=params.entry_price, error="IOC order not filled")
            else:
                error = result.get("response", {}).get("data", str(result))
                logger.error("Order failed: %s", error)
                return TradeResult(success=False, coin=params.coin, side=params.side, size=params.size, price=params.entry_price, error=str(error))

        except Exception as e:
            logger.exception("Order execution error")
            return TradeResult(success=False, coin=params.coin, side=params.side, size=params.size, price=params.entry_price, error=str(e))

    def _place_stop_loss(self, params: TradeParams) -> None:
        try:
            is_buy = params.side == "short"  # SL reverses direction
            trigger = {"triggerPx": str(params.stop_loss), "isMarket": True, "tpsl": "sl"}
            order_type = {"trigger": trigger}
            self._client.exchange.order(
                coin=params.coin,
                is_buy=is_buy,
                sz=params.size,
                limit_px=params.stop_loss,
                order_type=order_type,
                reduce_only=True,
            )
            logger.info("Stop loss set for %s at %.2f", params.coin, params.stop_loss)
        except Exception:
            logger.exception("Failed to set stop loss for %s", params.coin)

    def _place_take_profit(self, params: TradeParams) -> None:
        try:
            is_buy = params.side == "short"
            trigger = {"triggerPx": str(params.take_profit), "isMarket": True, "tpsl": "tp"}
            order_type = {"trigger": trigger}
            self._client.exchange.order(
                coin=params.coin,
                is_buy=is_buy,
                sz=params.size,
                limit_px=params.take_profit,
                order_type=order_type,
                reduce_only=True,
            )
            logger.info("Take profit set for %s at %.2f", params.coin, params.take_profit)
        except Exception:
            logger.exception("Failed to set take profit for %s", params.coin)

    def close_all_positions(self) -> list[TradeResult]:
        results = []
        state = self._client.get_account_state()
        for pos in state.positions:
            logger.info("Emergency closing position: %s %s (size=%.6f)", pos.side, pos.coin, pos.size)
            try:
                is_buy = pos.side == "short"
                market = self._client.get_market_info(pos.coin)

                slippage = 0.01
                if is_buy:
                    limit_price = round(market.mark_price * (1 + slippage), 2)
                else:
                    limit_price = round(market.mark_price * (1 - slippage), 2)

                result = self._client.exchange.order(
                    coin=pos.coin,
                    is_buy=is_buy,
                    sz=pos.size,
                    limit_px=limit_price,
                    order_type={"limit": {"tif": "Ioc"}},
                    reduce_only=True,
                )
                success = result.get("status") == "ok"
                results.append(TradeResult(
                    success=success,
                    coin=pos.coin,
                    side="close_" + pos.side,
                    size=pos.size,
                    price=market.mark_price,
                ))
            except Exception as e:
                logger.exception("Failed to close %s position", pos.coin)
                results.append(TradeResult(success=False, coin=pos.coin, side="close", size=pos.size, price=0, error=str(e)))
        return results
