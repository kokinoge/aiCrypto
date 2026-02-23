from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agents.journal import TradeJournal
from src.config import RiskConfig, SignalConfig

logger = logging.getLogger("trading_bot")

DEFAULT_PARAMS_PATH = Path(__file__).parent.parent.parent / "data" / "adaptive_params.json"
RECALC_INTERVAL_S = 30 * 60  # 30 minutes


@dataclass
class ParamOverrides:
    risk_per_trade_pct: float | None = None
    min_confidence: float | None = None
    coin_confidence_adjustments: dict[str, float] = field(default_factory=dict)
    skip_hours_utc: list[int] = field(default_factory=list)
    position_size_modifier: float = 1.0


# ── Safety bounds ─────────────────────────────────────────────────────

_RISK_MIN, _RISK_MAX = 1.0, 5.0
_CONF_MIN, _CONF_MAX = 0.4, 0.9
_SIZE_MIN, _SIZE_MAX = 0.5, 1.5


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ── Main class ────────────────────────────────────────────────────────


class AdaptiveParams:
    """Auto-adjusts trading parameters based on journal performance."""

    def __init__(
        self,
        journal: TradeJournal,
        base_risk: RiskConfig,
        base_signals: SignalConfig,
        path: Path | None = None,
    ) -> None:
        self._journal = journal
        self._base_risk = base_risk
        self._base_signals = base_signals
        self._path = path or DEFAULT_PARAMS_PATH
        self._overrides = self._load()
        self._last_calc: float = 0.0

    # ── Public API ────────────────────────────────────────────────────

    def recalculate(self) -> ParamOverrides:
        overrides = ParamOverrides()

        trades = self._journal.get_past_trades(limit=100)
        recent = trades[-10:]

        self._apply_streak_adjustment(recent, overrides)
        self._apply_win_rate_sizing(trades, overrides)
        self._apply_coin_confidence(trades, overrides)
        self._apply_hour_analysis(trades, overrides)
        self._enforce_bounds(overrides)

        self._overrides = overrides
        self._last_calc = time.monotonic()
        self._save(overrides)

        logger.info(
            "Adaptive params recalculated: risk=%.1f%%, conf=%s, size=%.2f, "
            "skip_hours=%s, coin_adj=%s",
            overrides.risk_per_trade_pct or self._base_risk.max_risk_per_trade_pct,
            overrides.min_confidence,
            overrides.position_size_modifier,
            overrides.skip_hours_utc or "none",
            overrides.coin_confidence_adjustments or "none",
        )
        return overrides

    def get_overrides(self) -> ParamOverrides:
        elapsed = time.monotonic() - self._last_calc
        if self._last_calc == 0.0 or elapsed >= RECALC_INTERVAL_S:
            return self.recalculate()
        return self._overrides

    def should_skip_now(self) -> tuple[bool, str]:
        overrides = self.get_overrides()
        hour = datetime.now(timezone.utc).hour
        if hour in overrides.skip_hours_utc:
            return True, f"Hour {hour} UTC skipped due to poor historical win rate"
        return False, ""

    def get_adjusted_confidence(self, coin: str, base_confidence: float) -> float:
        overrides = self.get_overrides()
        adjustment = overrides.coin_confidence_adjustments.get(coin, 0.0)
        return _clamp(base_confidence + adjustment, _CONF_MIN, _CONF_MAX)

    # ── Adjustment strategies ─────────────────────────────────────────

    def _apply_streak_adjustment(
        self, recent: list[dict[str, Any]], overrides: ParamOverrides
    ) -> None:
        if not recent:
            return

        base_risk = self._base_risk.max_risk_per_trade_pct
        base_conf = self._base_signals.min_confidence

        consecutive_wins = 0
        consecutive_losses = 0
        for trade in reversed(recent):
            pnl = trade.get("pnl", 0)
            if pnl > 0:
                if consecutive_losses > 0:
                    break
                consecutive_wins += 1
            else:
                if consecutive_wins > 0:
                    break
                consecutive_losses += 1

        if consecutive_losses >= 3:
            overrides.risk_per_trade_pct = base_risk * 0.5
            overrides.min_confidence = base_conf + 0.1
            logger.info(
                "Streak: %d consecutive losses → risk halved to %.1f%%, "
                "confidence raised to %.2f",
                consecutive_losses,
                overrides.risk_per_trade_pct,
                overrides.min_confidence,
            )
        elif consecutive_wins >= 3:
            overrides.risk_per_trade_pct = min(base_risk * 1.2, _RISK_MAX)
            logger.info(
                "Streak: %d consecutive wins → risk raised to %.1f%%",
                consecutive_wins,
                overrides.risk_per_trade_pct,
            )

    def _apply_win_rate_sizing(
        self, trades: list[dict[str, Any]], overrides: ParamOverrides
    ) -> None:
        total = len(trades)
        if total < 10:
            overrides.position_size_modifier = 0.8
            logger.info(
                "Win-rate sizing: only %d trades → conservative modifier 0.8", total
            )
            return

        stats = self._journal.get_win_rate()
        win_rate = stats.get("win_rate", 0.0)

        if win_rate >= 0.65:
            overrides.position_size_modifier = 1.2
        elif win_rate >= 0.55:
            overrides.position_size_modifier = 1.0
        elif win_rate < 0.45:
            overrides.position_size_modifier = 0.7
        else:
            overrides.position_size_modifier = 1.0

        logger.info(
            "Win-rate sizing: win_rate=%.2f → modifier=%.1f",
            win_rate,
            overrides.position_size_modifier,
        )

    def _apply_coin_confidence(
        self, trades: list[dict[str, Any]], overrides: ParamOverrides
    ) -> None:
        coin_trades: dict[str, list[float]] = defaultdict(list)
        for t in trades:
            coin = t.get("coin", "")
            if coin:
                coin_trades[coin].append(t.get("pnl", 0))

        for coin, pnls in coin_trades.items():
            if len(pnls) < 3:
                continue
            wins = sum(1 for p in pnls if p > 0)
            wr = wins / len(pnls)

            if wr < 0.3:
                overrides.coin_confidence_adjustments[coin] = 0.2
                logger.info(
                    "Coin adj: %s win_rate=%.2f → +0.2 confidence required", coin, wr
                )
            elif wr > 0.7:
                overrides.coin_confidence_adjustments[coin] = -0.1
                logger.info(
                    "Coin adj: %s win_rate=%.2f → -0.1 confidence (easier trigger)",
                    coin,
                    wr,
                )

    def _apply_hour_analysis(
        self, trades: list[dict[str, Any]], overrides: ParamOverrides
    ) -> None:
        hour_pnls: dict[int, list[float]] = defaultdict(list)
        for t in trades:
            ts = t.get("timestamp", "")
            try:
                dt = datetime.fromisoformat(ts)
                hour_pnls[dt.hour].append(t.get("pnl", 0))
            except (ValueError, TypeError):
                continue

        for hour, pnls in sorted(hour_pnls.items()):
            if len(pnls) < 3:
                continue
            wins = sum(1 for p in pnls if p > 0)
            wr = wins / len(pnls)
            if wr < 0.25:
                overrides.skip_hours_utc.append(hour)
                logger.info(
                    "Hour skip: UTC %02d:00 win_rate=%.2f (%d trades) → skipped",
                    hour,
                    wr,
                    len(pnls),
                )

    def _enforce_bounds(self, overrides: ParamOverrides) -> None:
        if overrides.risk_per_trade_pct is not None:
            overrides.risk_per_trade_pct = _clamp(
                overrides.risk_per_trade_pct, _RISK_MIN, _RISK_MAX
            )
        if overrides.min_confidence is not None:
            overrides.min_confidence = _clamp(
                overrides.min_confidence, _CONF_MIN, _CONF_MAX
            )
        overrides.position_size_modifier = _clamp(
            overrides.position_size_modifier, _SIZE_MIN, _SIZE_MAX
        )

    # ── Persistence ───────────────────────────────────────────────────

    def _load(self) -> ParamOverrides:
        if not self._path.exists():
            logger.debug("No adaptive params file found, using defaults")
            return ParamOverrides()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            overrides = ParamOverrides(
                risk_per_trade_pct=raw.get("risk_per_trade_pct"),
                min_confidence=raw.get("min_confidence"),
                coin_confidence_adjustments=raw.get("coin_confidence_adjustments", {}),
                skip_hours_utc=raw.get("skip_hours_utc", []),
                position_size_modifier=raw.get("position_size_modifier", 1.0),
            )
            logger.info("Loaded adaptive params from %s", self._path)
            return overrides
        except (json.JSONDecodeError, KeyError):
            logger.warning("Corrupt adaptive params file, using defaults: %s", self._path)
            return ParamOverrides()

    def _save(self, overrides: ParamOverrides) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(overrides)
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.debug("Saved adaptive params to %s", self._path)
