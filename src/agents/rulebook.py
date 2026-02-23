from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.hyperliquid.client import MarketInfo
from src.signals.engine import Signal

logger = logging.getLogger("trading_bot")

DEFAULT_RULES_PATH = Path(__file__).parent.parent.parent / "data" / "strategy_rules.json"

AUTO_DEACTIVATE_MIN_TRIGGERS = 10
AUTO_DEACTIVATE_THRESHOLD = 0.3


@dataclass
class StrategyRule:
    id: str
    description: str
    condition_type: str  # "coin", "funding_rate", "signal_amount", "time", "streak", "custom"
    condition: dict[str, Any]
    action: str  # "skip", "reduce_confidence", "reduce_size"
    action_value: float
    created_at: str
    source: str  # "ai_review", "weekly_review", "manual"
    times_triggered: int = 0
    times_correct: int = 0
    active: bool = True


@dataclass
class RuleMatch:
    rule: StrategyRule
    action: str
    value: float
    reason: str


class StrategyRulebook:
    """過去のトレードから学んだ戦略ルールを管理し、新しいシグナルに対して自動チェックする。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or DEFAULT_RULES_PATH
        self._rules: list[StrategyRule] = self._load()

    # ── Public API ────────────────────────────────────────────────────

    def check_signal(
        self,
        signal: Signal,
        market_info: MarketInfo | None = None,
    ) -> list[RuleMatch]:
        matches: list[RuleMatch] = []
        for rule in self._rules:
            if not rule.active:
                continue
            match = self._evaluate_rule(rule, signal, market_info)
            if match:
                matches.append(match)
        return matches

    def add_rule(self, rule: StrategyRule) -> None:
        self._rules.append(rule)
        self._save()
        logger.info("ルールブック: ルール追加 [%s] %s", rule.id, rule.description)

    def add_rule_from_ai(self, review_data: dict[str, Any]) -> StrategyRule | None:
        """PostTradeReviewerのAIレビュー出力から構造化ルールを生成する。"""
        adjustment = review_data.get("strategy_adjustment", "")
        if not adjustment:
            return None

        text = adjustment if isinstance(adjustment, str) else str(adjustment)
        text_lower = text.lower()

        rule = self._try_parse_coin_rule(text, text_lower)
        if not rule:
            rule = self._try_parse_funding_rule(text, text_lower)
        if not rule:
            rule = self._try_parse_custom_rule(text)

        if rule:
            self.add_rule(rule)
        return rule

    def deactivate_rule(self, rule_id: str) -> None:
        for rule in self._rules:
            if rule.id == rule_id:
                rule.active = False
                self._save()
                logger.info("ルールブック: ルール無効化 [%s]", rule_id)
                return
        logger.warning("ルールブック: ルールが見つかりません [%s]", rule_id)

    def get_active_rules(self) -> list[StrategyRule]:
        return [r for r in self._rules if r.active]

    def get_rule_stats(self) -> dict[str, Any]:
        active = [r for r in self._rules if r.active]
        inactive = [r for r in self._rules if not r.active]
        total_triggered = sum(r.times_triggered for r in self._rules)
        total_correct = sum(r.times_correct for r in self._rules)

        return {
            "total_rules": len(self._rules),
            "active": len(active),
            "inactive": len(inactive),
            "total_triggered": total_triggered,
            "total_correct": total_correct,
            "accuracy": round(total_correct / total_triggered, 2) if total_triggered else 0.0,
            "rules_by_type": self._count_by_type(),
        }

    def update_rule_outcome(self, rule_id: str, was_correct: bool) -> None:
        for rule in self._rules:
            if rule.id == rule_id:
                if was_correct:
                    rule.times_correct += 1
                self._auto_cleanup(rule)
                self._save()
                return

    # ── Rule evaluation ───────────────────────────────────────────────

    def _evaluate_rule(
        self,
        rule: StrategyRule,
        signal: Signal,
        market_info: MarketInfo | None,
    ) -> RuleMatch | None:
        checker = {
            "coin": self._check_coin,
            "funding_rate": self._check_funding_rate,
            "signal_amount": self._check_signal_amount,
            "time": self._check_time,
            "streak": self._check_streak,
            "custom": self._check_custom,
        }.get(rule.condition_type)

        if checker is None:
            return None
        return checker(rule, signal, market_info)

    def _check_coin(
        self, rule: StrategyRule, signal: Signal, _mi: MarketInfo | None,
    ) -> RuleMatch | None:
        target_coin = rule.condition.get("coin", "")
        if signal.coin != target_coin:
            return None
        rule.times_triggered += 1
        return RuleMatch(
            rule=rule,
            action=rule.action,
            value=rule.action_value,
            reason=f"{target_coin}に対するルール適用: {rule.description}",
        )

    def _check_funding_rate(
        self, rule: StrategyRule, signal: Signal, market_info: MarketInfo | None,
    ) -> RuleMatch | None:
        if market_info is None:
            return None
        direction = rule.condition.get("direction", "")
        threshold = rule.condition.get("funding_above", 0.0)
        if signal.side != direction:
            return None
        if abs(market_info.funding_rate * 100) <= threshold:
            return None
        rule.times_triggered += 1
        return RuleMatch(
            rule=rule,
            action=rule.action,
            value=rule.action_value,
            reason=f"ファンディングレート({market_info.funding_rate*100:.4f}%)が閾値{threshold}%を超過: {rule.description}",
        )

    def _check_signal_amount(
        self, rule: StrategyRule, signal: Signal, _mi: MarketInfo | None,
    ) -> RuleMatch | None:
        threshold = rule.condition.get("below_usd", 0)
        amount = _extract_usd_amount(signal.raw_message)
        if amount is None or amount >= threshold:
            return None
        rule.times_triggered += 1
        return RuleMatch(
            rule=rule,
            action=rule.action,
            value=rule.action_value,
            reason=f"シグナル金額(${amount:,.0f})が閾値${threshold:,.0f}未満: {rule.description}",
        )

    def _check_time(
        self, rule: StrategyRule, _sig: Signal, _mi: MarketInfo | None,
    ) -> RuleMatch | None:
        hours = rule.condition.get("hours_utc", [])
        current_hour = datetime.now(timezone.utc).hour
        if current_hour not in hours:
            return None
        rule.times_triggered += 1
        return RuleMatch(
            rule=rule,
            action=rule.action,
            value=rule.action_value,
            reason=f"現在のUTC時刻({current_hour}時)がルール対象時間帯: {rule.description}",
        )

    def _check_streak(
        self, rule: StrategyRule, _sig: Signal, _mi: MarketInfo | None,
    ) -> RuleMatch | None:
        from src.agents.journal import TradeJournal

        required = rule.condition.get("consecutive_losses", 0)
        if required <= 0:
            return None

        journal = TradeJournal()
        recent = journal.get_past_trades(limit=required)
        if len(recent) < required:
            return None
        if all(t.get("pnl", 0) <= 0 for t in recent):
            rule.times_triggered += 1
            return RuleMatch(
                rule=rule,
                action=rule.action,
                value=rule.action_value,
                reason=f"直近{required}回連続で損失が発生: {rule.description}",
            )
        return None

    def _check_custom(
        self, rule: StrategyRule, _sig: Signal, _mi: MarketInfo | None,
    ) -> RuleMatch | None:
        rule.times_triggered += 1
        return RuleMatch(
            rule=rule,
            action=rule.action,
            value=rule.action_value,
            reason=f"カスタムルール該当（AI評価推奨）: {rule.description}",
        )

    # ── AI review parsing ─────────────────────────────────────────────

    def _try_parse_coin_rule(self, text: str, text_lower: str) -> StrategyRule | None:
        skip_patterns = [
            (r"(\b[A-Z]{2,10}\b).*(?:避け|スキップ|avoid|skip)", "skip", 0.0),
            (r"(?:避け|スキップ|avoid|skip).*(\b[A-Z]{2,10}\b)", "skip", 0.0),
            (r"(\b[A-Z]{2,10}\b).*(?:注意|caution|careful)", "reduce_confidence", 0.3),
        ]
        for pattern, action, value in skip_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                coin = m.group(1).upper()
                if len(coin) < 2 or coin in {"THE", "AND", "FOR", "NOT", "BUT", "ARE"}:
                    continue
                return StrategyRule(
                    id=_gen_id(),
                    description=f"AIレビューに基づき{coin}の取引を制限: {text[:80]}",
                    condition_type="coin",
                    condition={"coin": coin},
                    action=action,
                    action_value=value,
                    created_at=_now_iso(),
                    source="ai_review",
                )
        return None

    def _try_parse_funding_rule(self, text: str, text_lower: str) -> StrategyRule | None:
        if "funding" not in text_lower and "ファンディング" not in text:
            return None

        rate_match = re.search(r"(\d+\.?\d*)\s*%", text)
        threshold = float(rate_match.group(1)) if rate_match else 0.05

        direction = "long"
        if any(kw in text_lower for kw in ("short", "ショート")):
            direction = "short"

        return StrategyRule(
            id=_gen_id(),
            description=f"ファンディングレート高時の{direction}を制限: {text[:80]}",
            condition_type="funding_rate",
            condition={"direction": direction, "funding_above": threshold},
            action="reduce_confidence",
            action_value=0.2,
            created_at=_now_iso(),
            source="ai_review",
        )

    def _try_parse_custom_rule(self, text: str) -> StrategyRule:
        return StrategyRule(
            id=_gen_id(),
            description=f"AIレビューからの戦略調整: {text[:120]}",
            condition_type="custom",
            condition={"pattern": text[:200]},
            action="reduce_confidence",
            action_value=0.1,
            created_at=_now_iso(),
            source="ai_review",
        )

    # ── Auto-cleanup ──────────────────────────────────────────────────

    def _auto_cleanup(self, rule: StrategyRule) -> None:
        if rule.times_triggered < AUTO_DEACTIVATE_MIN_TRIGGERS:
            return
        accuracy = rule.times_correct / rule.times_triggered
        if accuracy < AUTO_DEACTIVATE_THRESHOLD:
            rule.active = False
            logger.info(
                "ルールブック: 精度低下により自動無効化 [%s] (正答率=%.1f%%)",
                rule.id, accuracy * 100,
            )

    # ── Helpers ────────────────────────────────────────────────────────

    def _count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._rules:
            counts[r.condition_type] = counts.get(r.condition_type, 0) + 1
        return counts

    # ── Persistence ───────────────────────────────────────────────────

    def _load(self) -> list[StrategyRule]:
        if not self._path.exists():
            logger.debug("ルールブックファイルが見つかりません。新規作成: %s", self._path)
            return []

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return [
                StrategyRule(**entry)
                for entry in raw.get("rules", [])
            ]
        except (json.JSONDecodeError, KeyError, TypeError):
            logger.warning("ルールブックファイル破損。新規作成: %s", self._path)
            return []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"rules": [asdict(r) for r in self._rules]}
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


# ── Utility functions ─────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id() -> str:
    return f"rule_{uuid.uuid4().hex[:8]}"


def _extract_usd_amount(text: str) -> float | None:
    amounts = re.findall(r"\$?([\d,]+(?:\.\d+)?)", text)
    max_val = 0.0
    for raw in amounts:
        try:
            val = float(raw.replace(",", ""))
            if val > max_val:
                max_val = val
        except ValueError:
            continue
    return max_val if max_val > 0 else None
