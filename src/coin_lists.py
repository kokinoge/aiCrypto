from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Awaitable

logger = logging.getLogger("trading_bot")

DEFAULT_PATH = Path(__file__).parent.parent / "data" / "coin_lists.json"


@dataclass
class CoinListEntry:
    coin: str
    added_at: str
    reason: str = ""


@dataclass
class CoinListData:
    blacklist: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "blacklist"  # "blacklist" = default allow, exclude listed


class CoinListManager:
    """Manages coin blacklist with JSON persistence.

    Default behavior: All coins allowed. Blacklisted coins are excluded
    from signal processing and trade execution.
    """

    def __init__(
        self,
        path: Path | None = None,
        on_change: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._path = path or DEFAULT_PATH
        self._data = self._load()
        self._on_change = on_change  # WebSocket broadcast callback

    # -- Read operations --

    def get_blacklist(self) -> list[dict[str, Any]]:
        return list(self._data.blacklist)

    def get_blacklisted_coins(self) -> set[str]:
        return {entry["coin"] for entry in self._data.blacklist}

    def is_blacklisted(self, coin: str) -> bool:
        return coin.upper() in self.get_blacklisted_coins()

    def is_allowed(self, coin: str) -> bool:
        return not self.is_blacklisted(coin)

    # -- Write operations --

    async def add_to_blacklist(self, coin: str, reason: str = "") -> bool:
        coin = coin.upper().strip()
        if self.is_blacklisted(coin):
            return False

        entry = CoinListEntry(
            coin=coin,
            added_at=datetime.now(timezone.utc).isoformat(),
            reason=reason,
        )
        self._data.blacklist.append(asdict(entry))
        self._save()
        logger.info("Coin %s added to blacklist: %s", coin, reason)

        if self._on_change:
            await self._on_change()
        return True

    async def remove_from_blacklist(self, coin: str) -> bool:
        coin = coin.upper().strip()
        original_len = len(self._data.blacklist)
        self._data.blacklist = [
            e for e in self._data.blacklist if e["coin"] != coin
        ]
        if len(self._data.blacklist) == original_len:
            return False

        self._save()
        logger.info("Coin %s removed from blacklist", coin)

        if self._on_change:
            await self._on_change()
        return True

    # -- Persistence --

    def _load(self) -> CoinListData:
        if not self._path.exists():
            return CoinListData()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return CoinListData(
                blacklist=raw.get("blacklist", []),
                mode=raw.get("mode", "blacklist"),
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("Corrupt coin_lists.json, starting fresh")
            return CoinListData()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self._data)
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
