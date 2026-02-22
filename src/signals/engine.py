from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("trading_bot")

KNOWN_COINS = {
    "bitcoin": "BTC", "btc": "BTC",
    "ethereum": "ETH", "eth": "ETH",
    "solana": "SOL", "sol": "SOL",
    "dogecoin": "DOGE", "doge": "DOGE",
    "avalanche": "AVAX", "avax": "AVAX",
    "chainlink": "LINK", "link": "LINK",
    "polygon": "MATIC", "matic": "MATIC",
    "arbitrum": "ARB", "arb": "ARB",
    "optimism": "OP", "op": "OP",
    "sui": "SUI",
    "aptos": "APT", "apt": "APT",
    "pepe": "PEPE",
    "wif": "WIF",
    "render": "RNDR", "rndr": "RNDR",
    "injective": "INJ", "inj": "INJ",
    "sei": "SEI",
    "celestia": "TIA", "tia": "TIA",
    "jupiter": "JUP", "jup": "JUP",
    "pendle": "PENDLE",
}

BUY_KEYWORDS = [
    "buying", "bought", "accumulated", "accumulating",
    "inflow", "inflows", "adding", "added",
    "long", "bullish", "bid", "scooping",
    "purchased", "acquiring", "loading",
]

SELL_KEYWORDS = [
    "selling", "sold", "dumping", "dumped",
    "outflow", "outflows", "removing", "removed",
    "short", "bearish", "liquidating",
    "distributing", "exiting", "offloading",
]


@dataclass
class Signal:
    coin: str
    side: str  # "long" or "short"
    confidence: float  # 0.0 to 1.0
    source: str
    raw_message: str


class SignalEngine:
    """Parses Nansen Smart Alerts from Discord messages into actionable trading signals."""

    def __init__(self, tradeable_coins: list[str] | None = None):
        self._tradeable_coins = set(tradeable_coins or [])

    def update_tradeable_coins(self, coins: list[str]) -> None:
        self._tradeable_coins = set(coins)

    def parse_alert(self, message: str, source: str = "nansen") -> Signal | None:
        message_lower = message.lower()

        coin = self._extract_coin(message_lower, message)
        if not coin:
            logger.debug("No recognizable coin in message: %s", message[:100])
            return None

        if self._tradeable_coins and coin not in self._tradeable_coins:
            logger.debug("Coin %s not tradeable on Hyperliquid", coin)
            return None

        buy_score = sum(1 for kw in BUY_KEYWORDS if kw in message_lower)
        sell_score = sum(1 for kw in SELL_KEYWORDS if kw in message_lower)

        if buy_score == 0 and sell_score == 0:
            logger.debug("No buy/sell keywords in message for %s", coin)
            return None

        if buy_score > sell_score:
            side = "long"
            score = buy_score
        elif sell_score > buy_score:
            side = "short"
            score = sell_score
        else:
            logger.debug("Ambiguous signal for %s (buy=%d, sell=%d)", coin, buy_score, sell_score)
            return None

        confidence = min(score / 4.0, 1.0)

        # Boost for "smart money" or "fund" mentions
        if "smart money" in message_lower or "fund" in message_lower:
            confidence = min(confidence + 0.2, 1.0)
        if "whale" in message_lower:
            confidence = min(confidence + 0.15, 1.0)

        signal = Signal(
            coin=coin,
            side=side,
            confidence=round(confidence, 2),
            source=source,
            raw_message=message[:500],
        )
        logger.info("Signal detected: %s %s (confidence=%.2f)", side.upper(), coin, confidence)
        return signal

    def _extract_coin(self, message_lower: str, original: str) -> str | None:
        for name, ticker in KNOWN_COINS.items():
            pattern = rf"\b{re.escape(name)}\b"
            if re.search(pattern, message_lower):
                return ticker

        # Try to match $TICKER pattern
        ticker_match = re.search(r"\$([A-Z]{2,10})", original)
        if ticker_match:
            ticker = ticker_match.group(1)
            if not self._tradeable_coins or ticker in self._tradeable_coins:
                return ticker

        # Try uppercase standalone tickers
        for word in original.split():
            cleaned = word.strip(".,!?()[]{}:;\"'")
            if cleaned.isupper() and 2 <= len(cleaned) <= 10:
                if not self._tradeable_coins or cleaned in self._tradeable_coins:
                    return cleaned

        return None
