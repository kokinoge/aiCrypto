from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from src.config import BotConfig
from src.hyperliquid.client import AccountState, HyperliquidClient, MarketInfo, Position
from src.hyperliquid.risk import RiskManager, TradeParams
from src.hyperliquid.trader import TradeResult

logger = logging.getLogger("trading_bot")

PAPER_STATE_FILE = Path(__file__).parent.parent.parent / "data" / "paper_portfolio.json"


@dataclass
class PaperPosition:
    coin: str
    side: str
    size: float
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: float


@dataclass
class PaperPortfolio:
    initial_balance: float
    cash: float
    positions: list[PaperPosition] = field(default_factory=list)
    closed_trades: list[dict] = field(default_factory=list)
    total_pnl: float = 0.0


class PaperTrader:
    """Simulates trades using real market data without spending real money."""

    def __init__(self, config: BotConfig, client: HyperliquidClient, risk_manager: RiskManager):
        self._config = config
        self._client = client
        self._risk = risk_manager
        self._cooldowns: dict[str, float] = {}
        self._portfolio = self._load_or_create_portfolio()

    def _load_or_create_portfolio(self) -> PaperPortfolio:
        if PAPER_STATE_FILE.exists():
            try:
                data = json.loads(PAPER_STATE_FILE.read_text())
                positions = [PaperPosition(**p) for p in data.get("positions", [])]
                return PaperPortfolio(
                    initial_balance=data["initial_balance"],
                    cash=data["cash"],
                    positions=positions,
                    closed_trades=data.get("closed_trades", []),
                    total_pnl=data.get("total_pnl", 0.0),
                )
            except Exception:
                logger.warning("Failed to load paper portfolio, creating new one")

        balance = self._config.paper_trading_balance
        logger.info("Creating new paper portfolio with $%.2f", balance)
        return PaperPortfolio(initial_balance=balance, cash=balance)

    def _save_portfolio(self) -> None:
        PAPER_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "initial_balance": self._portfolio.initial_balance,
            "cash": self._portfolio.cash,
            "positions": [asdict(p) for p in self._portfolio.positions],
            "closed_trades": self._portfolio.closed_trades,
            "total_pnl": self._portfolio.total_pnl,
        }
        PAPER_STATE_FILE.write_text(json.dumps(data, indent=2))

    def get_account_state(self) -> AccountState:
        total_unrealized = 0.0
        total_margin = 0.0
        positions = []

        for pp in self._portfolio.positions:
            try:
                market = self._client.get_market_info(pp.coin)
                current_price = market.mark_price
            except Exception:
                current_price = pp.entry_price

            if pp.side == "long":
                pnl = (current_price - pp.entry_price) * pp.size
            else:
                pnl = (pp.entry_price - current_price) * pp.size

            margin = pp.size * pp.entry_price / self._config.risk.max_leverage
            total_unrealized += pnl
            total_margin += margin
            positions.append(Position(
                coin=pp.coin,
                size=pp.size,
                entry_price=pp.entry_price,
                unrealized_pnl=round(pnl, 2),
                leverage=float(self._config.risk.max_leverage),
                liquidation_price=None,
                side=pp.side,
            ))

        equity = self._portfolio.cash + total_margin + total_unrealized
        return AccountState(
            equity=round(equity, 2),
            margin_used=round(total_margin, 2),
            available_balance=round(self._portfolio.cash, 2),
            positions=positions,
        )

    def execute_signal(self, coin: str, side: str, confidence: float) -> TradeResult | None:
        if confidence < self._config.signals.min_confidence:
            return None

        pairs = self._config.trading_pairs
        if pairs and coin not in pairs:
            return None

        last = self._cooldowns.get(coin)
        if last and (time.time() - last) / 60 < self._config.signals.cooldown_minutes:
            logger.info("[PAPER] %s is on cooldown, skipping", coin)
            return None

        state = self.get_account_state()

        if len(state.positions) >= self._config.risk.max_positions:
            return TradeResult(success=False, coin=coin, side=side, size=0, price=0, error="Max positions reached")

        for pos in state.positions:
            if pos.coin == coin:
                logger.info("[PAPER] Already have position in %s, skipping", coin)
                return None

        dd = self._check_drawdown(state.equity)
        if dd:
            return TradeResult(success=False, coin=coin, side=side, size=0, price=0, error="Max drawdown exceeded")

        try:
            market = self._client.get_market_info(coin)
        except Exception as e:
            return TradeResult(success=False, coin=coin, side=side, size=0, price=0, error=f"Failed to get price: {e}")

        params = self._risk.calculate_trade_params(
            coin=coin, side=side, entry_price=market.mark_price, equity=state.equity,
        )

        position_cost = params.size * params.entry_price / self._config.risk.max_leverage
        if position_cost > self._portfolio.cash:
            return TradeResult(success=False, coin=coin, side=side, size=0, price=0, error="Insufficient paper balance")

        self._portfolio.positions.append(PaperPosition(
            coin=coin, side=side, size=params.size,
            entry_price=market.mark_price,
            stop_loss=params.stop_loss, take_profit=params.take_profit,
            opened_at=time.time(),
        ))
        self._portfolio.cash -= position_cost
        self._cooldowns[coin] = time.time()
        self._save_portfolio()

        logger.info(
            "[PAPER] Trade opened: %s %s | size=%.6f | entry=$%.2f | SL=$%.2f | TP=$%.2f",
            side.upper(), coin, params.size, market.mark_price, params.stop_loss, params.take_profit,
        )

        return TradeResult(
            success=True, coin=coin, side=side,
            size=params.size, price=market.mark_price, order_id="paper",
        )

    def check_sl_tp(self) -> list[tuple[PaperPosition, str, float]]:
        """Check all positions for stop loss / take profit hits. Returns closed positions."""
        closed = []
        remaining = []

        for pp in self._portfolio.positions:
            try:
                market = self._client.get_market_info(pp.coin)
                price = market.mark_price
            except Exception:
                remaining.append(pp)
                continue

            hit = None
            if pp.side == "long":
                if price <= pp.stop_loss:
                    hit = "STOP LOSS"
                elif price >= pp.take_profit:
                    hit = "TAKE PROFIT"
            else:
                if price >= pp.stop_loss:
                    hit = "STOP LOSS"
                elif price <= pp.take_profit:
                    hit = "TAKE PROFIT"

            if hit:
                if pp.side == "long":
                    pnl = (price - pp.entry_price) * pp.size
                else:
                    pnl = (pp.entry_price - price) * pp.size

                position_cost = pp.size * pp.entry_price / self._config.risk.max_leverage
                self._portfolio.cash += position_cost + pnl
                self._portfolio.total_pnl += pnl

                self._portfolio.closed_trades.append({
                    "coin": pp.coin, "side": pp.side,
                    "entry": pp.entry_price, "exit": price,
                    "size": pp.size, "pnl": round(pnl, 2),
                    "reason": hit, "closed_at": time.time(),
                })

                closed.append((pp, hit, round(pnl, 2)))
                logger.info(
                    "[PAPER] %s hit for %s %s | entry=$%.2f exit=$%.2f | PnL=$%.2f",
                    hit, pp.side.upper(), pp.coin, pp.entry_price, price, pnl,
                )
            else:
                remaining.append(pp)

        if closed:
            self._portfolio.positions = remaining
            self._save_portfolio()

        return closed

    def close_all_positions(self) -> list[TradeResult]:
        results = []
        for pp in self._portfolio.positions:
            try:
                market = self._client.get_market_info(pp.coin)
                price = market.mark_price
            except Exception:
                price = pp.entry_price

            if pp.side == "long":
                pnl = (price - pp.entry_price) * pp.size
            else:
                pnl = (pp.entry_price - price) * pp.size

            position_cost = pp.size * pp.entry_price / self._config.risk.max_leverage
            self._portfolio.cash += position_cost + pnl
            self._portfolio.total_pnl += pnl

            self._portfolio.closed_trades.append({
                "coin": pp.coin, "side": pp.side,
                "entry": pp.entry_price, "exit": price,
                "size": pp.size, "pnl": round(pnl, 2),
                "reason": "EMERGENCY CLOSE", "closed_at": time.time(),
            })

            results.append(TradeResult(success=True, coin=pp.coin, side=f"close_{pp.side}", size=pp.size, price=price))

        self._portfolio.positions = []
        self._save_portfolio()
        return results

    def get_summary(self) -> dict:
        state = self.get_account_state()
        return {
            "equity": state.equity,
            "cash": round(self._portfolio.cash, 2),
            "initial_balance": self._portfolio.initial_balance,
            "total_pnl": round(self._portfolio.total_pnl, 2),
            "return_pct": round((state.equity - self._portfolio.initial_balance) / self._portfolio.initial_balance * 100, 2),
            "open_positions": len(state.positions),
            "total_trades": len(self._portfolio.closed_trades),
            "positions": state.positions,
        }

    def _check_drawdown(self, equity: float) -> bool:
        dd_pct = ((self._portfolio.initial_balance - equity) / self._portfolio.initial_balance) * 100
        if dd_pct >= self._config.risk.max_drawdown_pct:
            logger.critical("[PAPER] MAX DRAWDOWN: %.1f%%", dd_pct)
            return True
        return False
