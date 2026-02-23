from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from src.hyperliquid.client import MarketInfo

logger = logging.getLogger("trading_bot")

MODEL = "grok-4-1-fast-non-reasoning"
BASE_URL = "https://api.x.ai/v1"

COIN_RESEARCH_CACHE_TTL = 900  # 15 minutes
MARKET_OVERVIEW_CACHE_TTL = 1800  # 30 minutes


@dataclass
class ResearchReport:
    coin: str
    sentiment: str  # "bullish", "bearish", "neutral"
    sentiment_score: float  # -1.0 to 1.0
    key_findings: list[str]
    risks: list[str]
    catalysts: list[str]
    recommendation: str  # "buy", "sell", "wait"
    confidence: float  # 0.0-1.0
    raw_analysis: str


@dataclass
class MarketOverview:
    overall_sentiment: str  # "risk_on", "risk_off", "neutral"
    btc_outlook: str  # "bullish", "bearish", "neutral"
    fear_greed: str  # "extreme_fear", "fear", "neutral", "greed", "extreme_greed"
    major_news: list[str]
    trading_environment: str  # "favorable", "caution", "avoid"
    summary: str


@dataclass
class TradeValidation:
    supported: bool
    confidence_adjustment: float  # -0.3 to +0.3
    reasoning: str
    twitter_sentiment: str
    warnings: list[str]


class _CacheEntry:
    __slots__ = ("value", "expires_at")

    def __init__(self, value: Any, ttl: float) -> None:
        self.value = value
        self.expires_at = time.monotonic() + ttl

    @property
    def expired(self) -> bool:
        return time.monotonic() >= self.expires_at


class GrokResearcher:
    """Uses xAI Grok API to research real-time crypto market conditions via X/Twitter data."""

    def __init__(self, api_key: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key, base_url=BASE_URL)
        self._cache: dict[str, _CacheEntry] = {}

    def _get_cached(self, key: str) -> Any | None:
        entry = self._cache.get(key)
        if entry is None or entry.expired:
            self._cache.pop(key, None)
            return None
        return entry.value

    def _set_cached(self, key: str, value: Any, ttl: float) -> None:
        self._cache[key] = _CacheEntry(value, ttl)

    async def _ask_grok(self, system: str, user: str) -> str | None:
        try:
            resp = await self._client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.3,
                max_tokens=1500,
            )
            return resp.choices[0].message.content
        except Exception:
            logger.warning("Grok API call failed", exc_info=True)
            return None

    def _parse_json(self, text: str) -> dict | None:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # drop opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse Grok JSON response: %s", text[:200])
            return None

    # ------------------------------------------------------------------
    # research_coin
    # ------------------------------------------------------------------

    async def research_coin(
        self, coin: str, side: str, market_info: MarketInfo | None = None
    ) -> ResearchReport | None:
        """Research a specific coin before trading using Grok's real-time X/Twitter access."""
        cache_key = f"coin:{coin}:{side}"
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        market_ctx = ""
        if market_info:
            market_ctx = (
                f"\n現在の市場データ:\n"
                f"- Mark Price: ${market_info.mark_price:,.4f}\n"
                f"- Funding Rate: {market_info.funding_rate:.6f}\n"
                f"- Open Interest: {market_info.open_interest:,.0f}\n"
            )

        system = (
            "あなたはプロの暗号通貨トレーダー兼リサーチアナリストです。"
            "リアルタイムのX/Twitterデータにアクセスできます。"
            "分析結果は必ず指定されたJSON形式で返してください。"
            "人間が読むフィールド（key_findings, risks, catalysts）は日本語で記述してください。"
        )

        user = (
            f"{coin}について、{side}ポジションの観点から徹底的にリサーチしてください。\n"
            f"{market_ctx}\n"
            f"以下を調査してください:\n"
            f"1. {coin}に関する最新のX/Twitterセンチメント\n"
            f"2. 価格に影響する最近のニュースやイベント\n"
            f"3. スマートマネーの動きがセンチメントと一致しているか\n"
            f"4. 今後24時間のリスクとカタリスト\n\n"
            f"最新のツイートで{coin}について確認してください: "
            f"ホエールアラート、取引所上場、プロトコルアップデート、FUDなど。\n\n"
            f"以下のJSON形式で回答してください:\n"
            f'{{\n'
            f'  "sentiment": "bullish" | "bearish" | "neutral",\n'
            f'  "sentiment_score": -1.0〜1.0の数値,\n'
            f'  "key_findings": ["発見1", "発見2", ...],\n'
            f'  "risks": ["リスク1", "リスク2", ...],\n'
            f'  "catalysts": ["カタリスト1", "カタリスト2", ...],\n'
            f'  "recommendation": "buy" | "sell" | "wait",\n'
            f'  "confidence": 0.0〜1.0の数値\n'
            f'}}'
        )

        raw = await self._ask_grok(system, user)
        if raw is None:
            return None

        data = self._parse_json(raw)
        if data is None:
            return None

        try:
            report = ResearchReport(
                coin=coin,
                sentiment=data.get("sentiment", "neutral"),
                sentiment_score=float(data.get("sentiment_score", 0.0)),
                key_findings=data.get("key_findings", []),
                risks=data.get("risks", []),
                catalysts=data.get("catalysts", []),
                recommendation=data.get("recommendation", "wait"),
                confidence=float(data.get("confidence", 0.5)),
                raw_analysis=raw,
            )
        except (ValueError, TypeError):
            logger.warning("Failed to build ResearchReport from Grok response")
            return None

        self._set_cached(cache_key, report, COIN_RESEARCH_CACHE_TTL)
        logger.info("Grok research for %s complete: %s (%.2f)", coin, report.sentiment, report.confidence)
        return report

    # ------------------------------------------------------------------
    # get_market_overview
    # ------------------------------------------------------------------

    async def get_market_overview(self) -> MarketOverview | None:
        """Get a general crypto market overview using Grok's real-time X/Twitter access."""
        cached = self._get_cached("market_overview")
        if cached is not None:
            return cached

        system = (
            "あなたはプロの暗号通貨マーケットアナリストです。"
            "リアルタイムのX/Twitterデータにアクセスできます。"
            "分析結果は必ず指定されたJSON形式で返してください。"
            "人間が読むフィールド（major_news, summary）は日本語で記述してください。"
        )

        user = (
            "現在の暗号通貨市場の全体像を分析してください:\n\n"
            "1. 市場全体のセンチメント（Fear & Greed）\n"
            "2. BTCのトレンドとドミナンス\n"
            "3. 今日の暗号通貨に影響する主要ニュース\n"
            "4. リスクオン/リスクオフの環境判断\n\n"
            "X/Twitterの最新の議論やトレンドを確認してください。\n\n"
            "以下のJSON形式で回答してください:\n"
            '{\n'
            '  "overall_sentiment": "risk_on" | "risk_off" | "neutral",\n'
            '  "btc_outlook": "bullish" | "bearish" | "neutral",\n'
            '  "fear_greed": "extreme_fear" | "fear" | "neutral" | "greed" | "extreme_greed",\n'
            '  "major_news": ["ニュース1", "ニュース2", ...],\n'
            '  "trading_environment": "favorable" | "caution" | "avoid",\n'
            '  "summary": "日本語での市場サマリー"\n'
            '}'
        )

        raw = await self._ask_grok(system, user)
        if raw is None:
            return None

        data = self._parse_json(raw)
        if data is None:
            return None

        try:
            overview = MarketOverview(
                overall_sentiment=data.get("overall_sentiment", "neutral"),
                btc_outlook=data.get("btc_outlook", "neutral"),
                fear_greed=data.get("fear_greed", "neutral"),
                major_news=data.get("major_news", []),
                trading_environment=data.get("trading_environment", "caution"),
                summary=data.get("summary", ""),
            )
        except (ValueError, TypeError):
            logger.warning("Failed to build MarketOverview from Grok response")
            return None

        self._set_cached("market_overview", overview, MARKET_OVERVIEW_CACHE_TTL)
        logger.info("Grok market overview: %s / %s", overview.overall_sentiment, overview.trading_environment)
        return overview

    # ------------------------------------------------------------------
    # validate_trade_idea
    # ------------------------------------------------------------------

    async def validate_trade_idea(
        self, coin: str, side: str, signal_source: str, confidence: float
    ) -> TradeValidation | None:
        """Validate a trade idea with Grok's real-time X/Twitter knowledge."""
        system = (
            "あなたはプロの暗号通貨トレーダーです。"
            "トレードアイデアを検証し、リアルタイムのX/Twitterデータを使って判断してください。"
            "分析結果は必ず指定されたJSON形式で返してください。"
            "人間が読むフィールド（reasoning, warnings）は日本語で記述してください。"
        )

        user = (
            f"以下のトレードアイデアを検証してください:\n\n"
            f"- コイン: {coin}\n"
            f"- 方向: {side}\n"
            f"- シグナルソース: {signal_source}\n"
            f"- 現在の信頼度: {confidence:.2f}\n\n"
            f"以下を確認してください:\n"
            f"1. このトレードは現在の市場ナラティブに合っているか?\n"
            f"2. X/Twitterに矛盾する情報はないか?\n"
            f"3. タイミング: 今がエントリーに適切か、待つべきか?\n\n"
            f"{coin}に関する最新のツイート、ホエールアラート、"
            f"取引所の動き、プロトコルの更新を確認してください。\n\n"
            f"以下のJSON形式で回答してください:\n"
            f'{{\n'
            f'  "supported": true | false,\n'
            f'  "confidence_adjustment": -0.3〜+0.3の数値,\n'
            f'  "reasoning": "日本語での判断理由",\n'
            f'  "twitter_sentiment": "positive" | "negative" | "mixed" | "neutral",\n'
            f'  "warnings": ["警告1", "警告2", ...]\n'
            f'}}'
        )

        raw = await self._ask_grok(system, user)
        if raw is None:
            return None

        data = self._parse_json(raw)
        if data is None:
            return None

        try:
            adj = float(data.get("confidence_adjustment", 0.0))
            adj = max(-0.3, min(0.3, adj))
            validation = TradeValidation(
                supported=bool(data.get("supported", False)),
                confidence_adjustment=adj,
                reasoning=data.get("reasoning", ""),
                twitter_sentiment=data.get("twitter_sentiment", "neutral"),
                warnings=data.get("warnings", []),
            )
        except (ValueError, TypeError):
            logger.warning("Failed to build TradeValidation from Grok response")
            return None

        logger.info(
            "Grok trade validation for %s %s: supported=%s adj=%.2f",
            side, coin, validation.supported, validation.confidence_adjustment,
        )
        return validation


def create_researcher(api_key: str) -> GrokResearcher | None:
    """Factory that returns None when no API key is configured."""
    if not api_key:
        logger.warning("XAI_API_KEY not set — GrokResearcher disabled")
        return None
    return GrokResearcher(api_key)
