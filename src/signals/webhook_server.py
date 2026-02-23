from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiohttp import web

from src.config import BotConfig
from src.signals.engine import Signal, SignalEngine

logger = logging.getLogger("trading_bot")

VALID_SIDES = {"long", "short"}
DASHBOARD_HTML = Path(__file__).parent.parent / "web" / "dashboard.html"


class WebhookServer:
    """HTTP webhook server with trading dashboard.

    Endpoints:
        GET  /            — Trading dashboard UI
        GET  /health      — Bot health check
        GET  /api/dashboard — Dashboard data API
        POST /webhook/nansen  — Nansen Smart Alert webhook
        POST /webhook/custom  — Manual signal
    """

    def __init__(
        self,
        config: BotConfig,
        signal_engine: SignalEngine,
        on_signal: Callable[[Signal], Awaitable[None]],
        get_dashboard_data: Callable[[], dict[str, Any]] | None = None,
    ):
        self._config = config
        self._engine = signal_engine
        self._on_signal = on_signal
        self._get_dashboard_data = get_dashboard_data
        self._start_time = time.time()
        self._signals_received = 0

        self._app = web.Application()
        self._app.router.add_get("/", self._handle_dashboard)
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/api/dashboard", self._handle_dashboard_api)
        self._app.router.add_post("/webhook/nansen", self._handle_nansen)
        self._app.router.add_post("/webhook/custom", self._handle_custom)
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        port = self._config.webhook_port
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", port)
        await site.start()
        logger.info("Webhook server listening on http://0.0.0.0:%d", port)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            logger.info("Webhook server stopped")

    # ------------------------------------------------------------------
    # GET /health
    # ------------------------------------------------------------------

    async def _handle_dashboard(self, request: web.Request) -> web.Response:
        if DASHBOARD_HTML.exists():
            return web.Response(
                text=DASHBOARD_HTML.read_text(encoding="utf-8"),
                content_type="text/html",
            )
        return web.Response(text="Dashboard not found", status=404)

    async def _handle_health(self, request: web.Request) -> web.Response:
        uptime = int(time.time() - self._start_time)
        return web.json_response({
            "status": "ok",
            "mode": self._config.mode,
            "uptime_seconds": uptime,
            "signals_received": self._signals_received,
        })

    async def _handle_dashboard_api(self, request: web.Request) -> web.Response:
        if self._get_dashboard_data:
            try:
                data = self._get_dashboard_data()
                data["last_updated"] = datetime.now(timezone.utc).isoformat()
                return web.json_response(data)
            except Exception:
                logger.exception("Error generating dashboard data")
        return web.json_response({
            "status": "running",
            "mode": self._config.mode,
            "equity": 0, "cash": 0, "initial_balance": 0,
            "total_pnl": 0, "return_pct": 0,
            "open_positions": [], "closed_trades": [],
            "win_rate": {"total": 0, "wins": 0, "losses": 0, "win_rate": 0.0},
            "active_rules": 0, "streak": ["none", 0],
            "position_size_modifier": 1.0, "lessons": [],
            "agent_accuracy": {},
            "last_updated": datetime.now(timezone.utc).isoformat(),
        })

    # ------------------------------------------------------------------
    # POST /webhook/nansen
    # ------------------------------------------------------------------

    async def _handle_nansen(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response({"error": "invalid JSON"}, status=400)

        message = self._extract_nansen_text(body)
        if not message:
            return web.json_response({"error": "no parseable text in payload"}, status=400)

        signal = self._engine.parse_alert(message, source="webhook-nansen")
        if signal is None:
            return web.json_response({
                "accepted": False,
                "reason": "no actionable signal detected in payload",
            })

        self._signals_received += 1
        logger.info("Webhook nansen signal: %s %s (conf=%.2f)", signal.side, signal.coin, signal.confidence)
        await self._on_signal(signal)

        return web.json_response({
            "accepted": True,
            "coin": signal.coin,
            "side": signal.side,
            "confidence": signal.confidence,
        })

    # ------------------------------------------------------------------
    # POST /webhook/custom
    # ------------------------------------------------------------------

    async def _handle_custom(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response({"error": "invalid JSON"}, status=400)

        coin = body.get("coin", "").upper().strip()
        side = body.get("side", "").lower().strip()
        confidence = body.get("confidence", 0.8)
        message = body.get("message", "")

        if not coin:
            return web.json_response({"error": "missing 'coin' field"}, status=400)
        if side not in VALID_SIDES:
            return web.json_response(
                {"error": f"'side' must be one of {sorted(VALID_SIDES)}"}, status=400,
            )
        if not (0.0 <= confidence <= 1.0):
            return web.json_response({"error": "'confidence' must be between 0.0 and 1.0"}, status=400)

        signal = Signal(
            coin=coin,
            side=side,
            confidence=round(float(confidence), 2),
            source="webhook-custom",
            raw_message=message[:500] if message else f"Manual signal: {side} {coin}",
        )

        self._signals_received += 1
        logger.info("Webhook custom signal: %s %s (conf=%.2f)", signal.side, signal.coin, signal.confidence)
        await self._on_signal(signal)

        return web.json_response({
            "accepted": True,
            "coin": signal.coin,
            "side": signal.side,
            "confidence": signal.confidence,
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_nansen_text(payload: dict) -> str:
        """Best-effort extraction of human-readable text from a Nansen webhook payload."""
        parts: list[str] = []

        for key in ("content", "text", "message", "description", "title", "alert"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                parts.append(val.strip())

        # Discord-style embeds nested in the payload
        for embed in payload.get("embeds", []):
            if isinstance(embed, dict):
                for k in ("title", "description"):
                    v = embed.get(k)
                    if isinstance(v, str) and v.strip():
                        parts.append(v.strip())
                for field in embed.get("fields", []):
                    if isinstance(field, dict):
                        name = field.get("name", "")
                        value = field.get("value", "")
                        if name:
                            parts.append(str(name))
                        if value:
                            parts.append(str(value))

        # If payload has a generic "data" dict, recurse one level
        data = payload.get("data")
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, str) and v.strip():
                    parts.append(v.strip())

        return " ".join(parts)
