from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("trading_bot")

KNOWN_COINS = {
    "bitcoin": "BTC", "btc": "BTC",
    "ethereum": "ETH", "eth": "ETH", "weth": "ETH",
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

        nansen_signal = self._parse_nansen_smart_alert(message_lower, message)
        if nansen_signal:
            return nansen_signal

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

        if "smart money" in message_lower or "fund" in message_lower:
            confidence = min(confidence + 0.2, 1.0)
        if "whale" in message_lower:
            confidence = min(confidence + 0.15, 1.0)
        if "smart alert" in message_lower:
            confidence = min(confidence + 0.3, 1.0)

        signal = Signal(
            coin=coin,
            side=side,
            confidence=round(confidence, 2),
            source=source,
            raw_message=message[:500],
        )
        logger.info("Signal detected: %s %s (confidence=%.2f)", side.upper(), coin, confidence)
        return signal

    def _parse_nansen_smart_alert(self, message_lower: str, original: str) -> Signal | None:
        """Detect Nansen Smart Alert format: 'Smart Alert: discord' with Inflow/Outflow data."""
        if "smart alert" not in message_lower:
            return None

        coins_found: list[str] = []
        for name, ticker in KNOWN_COINS.items():
            if re.search(rf"\b{re.escape(name)}\b", message_lower):
                if ticker not in coins_found:
                    coins_found.append(ticker)

        for word in original.split():
            cleaned = word.strip(".,!?()[]{}:;\"'")
            if cleaned.isupper() and 2 <= len(cleaned) <= 10:
                mapped = KNOWN_COINS.get(cleaned.lower(), cleaned)
                if mapped not in coins_found:
                    if not self._tradeable_coins or mapped in self._tradeable_coins:
                        coins_found.append(mapped)

        if not coins_found:
            logger.debug("Nansen Smart Alert but no coin found: %s", original[:100])
            return None

        coin = coins_found[0]
        if self._tradeable_coins and coin not in self._tradeable_coins:
            for c in coins_found[1:]:
                if c in self._tradeable_coins:
                    coin = c
                    break
            else:
                logger.debug("Nansen Smart Alert coins not tradeable: %s", coins_found)
                return None

        has_inflow = "inflow" in message_lower
        has_outflow = "outflow" in message_lower

        if has_inflow and not has_outflow:
            side = "long"
        elif has_outflow and not has_inflow:
            side = "short"
        elif has_inflow and has_outflow:
            inflow_amounts = re.findall(r"inflow[:\s]*\$?([\d,.]+)", message_lower)
            outflow_amounts = re.findall(r"outflow[:\s]*\$?([\d,.]+)", message_lower)
            total_in = sum(float(a.replace(",", "")) for a in inflow_amounts) if inflow_amounts else 0
            total_out = sum(float(a.replace(",", "")) for a in outflow_amounts) if outflow_amounts else 0
            side = "long" if total_in >= total_out else "short"
        else:
            logger.debug("Nansen Smart Alert but no inflow/outflow: %s", original[:100])
            return None

        amount_match = re.findall(r"\$?([\d,]+(?:\.\d+)?)\s*(?:m|b)?", message_lower)
        total_usd = 0.0
        for amt in amount_match:
            try:
                val = float(amt.replace(",", ""))
                if val > 10000:
                    total_usd += val
            except ValueError:
                continue

        confidence = 0.7
        if total_usd > 500_000:
            confidence = 0.8
        if total_usd > 1_000_000:
            confidence = 0.85
        if total_usd > 5_000_000:
            confidence = 0.9

        signal = Signal(
            coin=coin,
            side=side,
            confidence=confidence,
            source="nansen-smart-alert",
            raw_message=original[:500],
        )
        logger.info(
            "Nansen Smart Alert detected: %s %s (amount=$%.0f, confidence=%.2f)",
            side.upper(), coin, total_usd, confidence,
        )
        return signal

    def _extract_coin(self, message_lower: str, original: str) -> str | None:
        for name, ticker in KNOWN_COINS.items():
            pattern = rf"\b{re.escape(name)}\b"
            if re.search(pattern, message_lower):
                return ticker

        ticker_match = re.search(r"\$([A-Z]{2,10})", original)
        if ticker_match:
            ticker = ticker_match.group(1)
            if not self._tradeable_coins or ticker in self._tradeable_coins:
                return ticker

        for word in original.split():
            cleaned = word.strip(".,!?()[]{}:;\"'")
            if cleaned.isupper() and 2 <= len(cleaned) <= 10:
                if not self._tradeable_coins or cleaned in self._tradeable_coins:
                    return cleaned

        return None
