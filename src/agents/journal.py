from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("trading_bot")

DEFAULT_JOURNAL_PATH = Path(__file__).parent.parent.parent / "data" / "trade_journal.json"
MAX_ENTRIES = 100


@dataclass
class AnalysisRecord:
    timestamp: str
    coin: str
    side: str
    confidence: float
    source: str
    agent_analyses: dict[str, Any]
    final_decision: dict[str, Any]


@dataclass
class TradeResult:
    timestamp: str
    coin: str
    side: str
    entry_price: float
    exit_price: float
    pnl: float
    reason: str


@dataclass
class ReviewRecord:
    timestamp: str
    coin: str
    review_data: dict[str, Any]


@dataclass
class JournalData:
    analyses: list[dict[str, Any]] = field(default_factory=list)
    trades: list[dict[str, Any]] = field(default_factory=list)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    lessons: list[dict[str, Any]] = field(default_factory=list)


class TradeJournal:
    """Persisted trade learning journal for agent team memory."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_JOURNAL_PATH
        self._data = self._load()

    # ── Write operations ──────────────────────────────────────────────

    def record_analysis(
        self,
        signal: dict[str, Any],
        agent_analyses: dict[str, Any],
        final_decision: dict[str, Any],
    ) -> None:
        record = AnalysisRecord(
            timestamp=_now_iso(),
            coin=signal.get("coin", "UNKNOWN"),
            side=signal.get("side", "unknown"),
            confidence=signal.get("confidence", 0.0),
            source=signal.get("source", "unknown"),
            agent_analyses=agent_analyses,
            final_decision=final_decision,
        )
        self._data.analyses.append(asdict(record))
        self._rotate(self._data.analyses)
        self._save()
        logger.info("Journal: recorded analysis for %s %s", record.side.upper(), record.coin)

    def record_trade_result(
        self,
        coin: str,
        side: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        reason: str,
    ) -> None:
        record = TradeResult(
            timestamp=_now_iso(),
            coin=coin,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            reason=reason,
        )
        self._data.trades.append(asdict(record))
        self._rotate(self._data.trades)
        self._save()
        logger.info("Journal: recorded trade result %s %s pnl=%.2f", side.upper(), coin, pnl)

    def record_review(self, coin: str, review_data: dict[str, Any]) -> None:
        record = ReviewRecord(
            timestamp=_now_iso(),
            coin=coin,
            review_data=review_data,
        )
        self._data.reviews.append(asdict(record))
        self._rotate(self._data.reviews)

        lesson = review_data.get("lesson")
        if lesson:
            self._data.lessons.append({
                "timestamp": record.timestamp,
                "coin": coin,
                "lesson": lesson,
            })
            self._rotate(self._data.lessons)

        self._save()
        logger.info("Journal: recorded review for %s", coin)

    # ── Read operations ───────────────────────────────────────────────

    def get_past_trades(self, coin: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        trades = self._data.trades
        if coin:
            trades = [t for t in trades if t.get("coin") == coin]
        return trades[-limit:]

    def get_lessons(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._data.lessons[-limit:]

    def get_win_rate(self) -> dict[str, Any]:
        trades = self._data.trades
        if not trades:
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0}

        wins = [t for t in trades if t.get("pnl", 0) > 0]
        losses = [t for t in trades if t.get("pnl", 0) <= 0]

        avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0.0

        return {
            "total": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(trades), 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
        }

    def get_performance_by_signal_type(self) -> dict[str, dict[str, Any]]:
        source_map: dict[str, list[float]] = {}

        analysis_sources: dict[tuple[str, str], str] = {}
        for a in self._data.analyses:
            key = (a.get("coin", ""), a.get("side", ""))
            analysis_sources[key] = a.get("source", "unknown")

        for t in self._data.trades:
            key = (t.get("coin", ""), t.get("side", ""))
            source = analysis_sources.get(key, "unknown")
            source_map.setdefault(source, []).append(t.get("pnl", 0))

        result: dict[str, dict[str, Any]] = {}
        for source, pnls in source_map.items():
            wins = sum(1 for p in pnls if p > 0)
            result[source] = {
                "total": len(pnls),
                "wins": wins,
                "losses": len(pnls) - wins,
                "win_rate": round(wins / len(pnls), 2) if pnls else 0.0,
                "total_pnl": round(sum(pnls), 2),
            }
        return result

    def build_context_for_agents(self, days: int = 30) -> str:
        stats = self.get_win_rate()
        if stats["total"] == 0:
            return "Past Performance: No trade history yet."

        cutoff = datetime.now(timezone.utc).timestamp() - days * 86400
        recent = [
            t for t in self._data.trades
            if _parse_ts(t.get("timestamp", "")) >= cutoff
        ]
        if not recent:
            return f"Past Performance (last {days} days): No trades in this period."

        wins = [t for t in recent if t.get("pnl", 0) > 0]
        losses = [t for t in recent if t.get("pnl", 0) <= 0]
        win_rate = round(len(wins) / len(recent) * 100) if recent else 0
        avg_win = round(sum(t["pnl"] for t in wins) / len(wins), 2) if wins else 0.0
        avg_loss = round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0.0

        best = max(recent, key=lambda t: t.get("pnl", 0))
        worst = min(recent, key=lambda t: t.get("pnl", 0))

        lines = [
            f"Past Performance (last {days} days):",
            f"- Win rate: {win_rate}% ({len(wins)}W / {len(losses)}L)",
            f"- Average profit: +${abs(avg_win):.2f} / Average loss: -${abs(avg_loss):.2f}",
            f"- Best trade: {best['side'].upper()} {best['coin']} +${best['pnl']:.2f}",
            f"- Worst trade: {worst['side'].upper()} {worst['coin']} ${worst['pnl']:.2f}",
        ]

        lessons = self.get_lessons(limit=5)
        if lessons:
            lesson_texts = [l["lesson"] for l in lessons if l.get("lesson")]
            if lesson_texts:
                lines.append(f"- Lessons: {'; '.join(lesson_texts)}")

        signal_perf = self.get_performance_by_signal_type()
        if signal_perf:
            parts = [f"{src} {d['win_rate']:.0%}" for src, d in signal_perf.items()]
            lines.append(f"- Signal accuracy by source: {', '.join(parts)}")

        return "\n".join(lines)

    # ── Persistence helpers ───────────────────────────────────────────

    def _load(self) -> JournalData:
        if not self._path.exists():
            logger.debug("Journal file not found, starting fresh: %s", self._path)
            return JournalData()

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return JournalData(
                analyses=raw.get("analyses", []),
                trades=raw.get("trades", []),
                reviews=raw.get("reviews", []),
                lessons=raw.get("lessons", []),
            )
        except (json.JSONDecodeError, KeyError):
            logger.warning("Corrupt journal file, starting fresh: %s", self._path)
            return JournalData()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self._data)
        self._path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _rotate(entries: list[Any]) -> None:
        if len(entries) > MAX_ENTRIES:
            del entries[: len(entries) - MAX_ENTRIES]


# ── Utility functions ─────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_ts(iso_str: str) -> float:
    try:
        return datetime.fromisoformat(iso_str).timestamp()
    except (ValueError, TypeError):
        return 0.0
