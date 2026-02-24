from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from src.config import BotConfig

logger = logging.getLogger("trading_bot")


@dataclass
class MarketInfo:
    coin: str
    mark_price: float
    mid_price: float
    funding_rate: float
    open_interest: float


@dataclass
class Position:
    coin: str
    size: float
    entry_price: float
    unrealized_pnl: float
    leverage: float
    liquidation_price: float | None
    side: str  # "long" or "short"


@dataclass
class AccountState:
    equity: float
    margin_used: float
    available_balance: float
    positions: list[Position]


class HyperliquidClient:
    """Wrapper around the Hyperliquid SDK for clean access to market data and account info."""

    def __init__(self, config: BotConfig):
        self._config = config
        base_url = constants.TESTNET_API_URL if config.is_testnet else constants.MAINNET_API_URL
        self._info = Info(base_url, skip_ws=True)
        self._exchange: Exchange | None = None
        self._base_url = base_url

        if config.hl_secret_key:
            self._exchange = Exchange(
                wallet=None,
                base_url=base_url,
                account_address=config.hl_account_address or None,
            )
            self._exchange.account_address = config.hl_account_address
        logger.info("Hyperliquid client initialized (mode=%s)", config.mode)

    @property
    def info(self) -> Info:
        return self._info

    @property
    def exchange(self) -> Exchange:
        if self._exchange is None:
            raise RuntimeError("Exchange not initialized — HL_SECRET_KEY is required for trading")
        return self._exchange

    def get_all_markets(self) -> list[dict[str, Any]]:
        meta = self._info.meta()
        return meta.get("universe", [])

    def get_tradeable_coins(self) -> list[str]:
        return [m["name"] for m in self.get_all_markets()]

    def get_market_info(self, coin: str) -> MarketInfo:
        ctx_list = self._info.meta_and_asset_ctxs()
        universe = ctx_list[0]["universe"]
        asset_ctxs = ctx_list[1]

        idx = None
        for i, u in enumerate(universe):
            if u["name"] == coin:
                idx = i
                break
        if idx is None:
            raise ValueError(f"Coin '{coin}' not found on Hyperliquid")

        ctx = asset_ctxs[idx]
        return MarketInfo(
            coin=coin,
            mark_price=float(ctx["markPx"]),
            mid_price=float(ctx["midPx"]) if "midPx" in ctx else float(ctx["markPx"]),
            funding_rate=float(ctx["funding"]),
            open_interest=float(ctx["openInterest"]),
        )

    def get_all_coins_with_market_data(self) -> list[MarketInfo]:
        """Fetch market data for all tradeable coins in a single API call."""
        ctx_list = self._info.meta_and_asset_ctxs()
        universe = ctx_list[0]["universe"]
        asset_ctxs = ctx_list[1]

        results = []
        for i, u in enumerate(universe):
            if i >= len(asset_ctxs):
                break
            ctx = asset_ctxs[i]
            try:
                mark_px = float(ctx["markPx"])
                mid_px_raw = ctx.get("midPx")
                mid_px = float(mid_px_raw) if mid_px_raw is not None else mark_px
                results.append(MarketInfo(
                    coin=u["name"],
                    mark_price=mark_px,
                    mid_price=mid_px,
                    funding_rate=float(ctx["funding"]),
                    open_interest=float(ctx["openInterest"]),
                ))
            except (KeyError, ValueError, TypeError):
                continue
        return results

    def get_account_state(self) -> AccountState:
        address = self._config.hl_account_address
        if not address:
            raise RuntimeError("HL_ACCOUNT_ADDRESS is required")

        state = self._info.user_state(address)
        summary = state["marginSummary"]

        positions = []
        for ap in state.get("assetPositions", []):
            pos = ap["position"]
            size = float(pos["szi"])
            if size == 0:
                continue
            positions.append(Position(
                coin=pos["coin"],
                size=abs(size),
                entry_price=float(pos["entryPx"]),
                unrealized_pnl=float(pos["unrealizedPnl"]),
                leverage=float(pos.get("leverage", {}).get("value", 1)),
                liquidation_price=float(pos["liquidationPx"]) if pos.get("liquidationPx") else None,
                side="long" if size > 0 else "short",
            ))

        return AccountState(
            equity=float(summary["accountValue"]),
            margin_used=float(summary["totalMarginUsed"]),
            available_balance=float(summary["accountValue"]) - float(summary["totalMarginUsed"]),
            positions=positions,
        )

    def get_open_orders(self) -> list[dict[str, Any]]:
        address = self._config.hl_account_address
        if not address:
            return []
        return self._info.open_orders(address)
