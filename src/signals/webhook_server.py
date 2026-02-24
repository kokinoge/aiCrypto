from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiohttp import web, WSMsgType

from src.coin_lists import CoinListManager
from src.config import BotConfig
from src.signals.engine import Signal, SignalEngine

logger = logging.getLogger("trading_bot")

VALID_SIDES = {"long", "short"}
DASHBOARD_HTML = Path(__file__).parent.parent / "web" / "dashboard.html"
FRONTEND_BUILD_DIR = Path(__file__).parent.parent.parent / "frontend" / "out"


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
        get_all_coins_data: Callable[[], list[dict[str, Any]]] | None = None,
        coin_list_manager: CoinListManager | None = None,
    ):
        self._config = config
        self._engine = signal_engine
        self._on_signal = on_signal
        self._get_dashboard_data = get_dashboard_data
        self._get_all_coins_data = get_all_coins_data
        self._coin_list_manager = coin_list_manager
        self._start_time = time.time()
        self._signals_received = 0
        self._ws_clients: set[web.WebSocketResponse] = set()

        self._app = web.Application(middlewares=[self._cors_middleware])
        self._app.router.add_get("/", self._handle_dashboard)
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/api/dashboard", self._handle_dashboard_api)
        self._app.router.add_post("/webhook/nansen", self._handle_nansen)
        self._app.router.add_post("/webhook/custom", self._handle_custom)
        # WebSocket
        self._app.router.add_get("/ws", self._handle_ws)
        # Coin management API
        self._app.router.add_get("/api/coins", self._handle_get_coins)
        self._app.router.add_get("/api/coins/blacklist", self._handle_get_blacklist)
        self._app.router.add_post("/api/coins/blacklist", self._handle_add_blacklist)
        self._app.router.add_delete("/api/coins/blacklist/{coin}", self._handle_remove_blacklist)
        # Static assets for React frontend (_next/static/*, etc.)
        if FRONTEND_BUILD_DIR.exists():
            next_assets = FRONTEND_BUILD_DIR / "_next"
            if next_assets.exists():
                self._app.router.add_static("/_next", next_assets)
            # Catch-all for frontend pages (must be last)
            self._app.router.add_get("/{path:.*}", self._handle_frontend_fallback)
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
        # Prefer React frontend
        react_index = FRONTEND_BUILD_DIR / "index.html"
        if react_index.exists():
            return web.FileResponse(react_index)
        # Fallback to legacy HTML dashboard
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
    # CORS middleware
    # ------------------------------------------------------------------

    @web.middleware
    async def _cors_middleware(self, request: web.Request, handler: Callable) -> web.Response:
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            response = await handler(request)
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET,POST,DELETE,OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    # ------------------------------------------------------------------
    # WebSocket  GET /ws
    # ------------------------------------------------------------------

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30.0)
        await ws.prepare(request)
        self._ws_clients.add(ws)
        logger.info("WebSocket client connected (%d total)", len(self._ws_clients))

        # Send initial state on connect
        try:
            initial: dict[str, Any] = {"type": "initial_state", "data": {}, "timestamp": datetime.now(timezone.utc).isoformat()}
            if self._get_dashboard_data:
                try:
                    initial["data"]["dashboard"] = self._get_dashboard_data()
                except Exception:
                    logger.exception("Error getting dashboard data for WS initial state")
            if self._get_all_coins_data:
                try:
                    initial["data"]["coins"] = self._get_all_coins_data()
                except Exception:
                    logger.exception("Error getting coins data for WS initial state")
            if self._coin_list_manager:
                initial["data"]["blacklist"] = self._coin_list_manager.get_blacklist()
            await ws.send_str(json.dumps(initial))
        except Exception:
            logger.exception("Error sending WS initial state")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        payload = json.loads(msg.data)
                        msg_type = payload.get("type", "")
                    except (json.JSONDecodeError, AttributeError):
                        continue

                    if msg_type == "request_dashboard":
                        data = {}
                        if self._get_dashboard_data:
                            try:
                                data = self._get_dashboard_data()
                            except Exception:
                                logger.exception("Error getting dashboard data for WS request")
                        await ws.send_str(json.dumps({
                            "type": "dashboard_update",
                            "data": data,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }))

                    elif msg_type == "request_coins":
                        data: list[dict[str, Any]] = []
                        if self._get_all_coins_data:
                            try:
                                data = self._get_all_coins_data()
                            except Exception:
                                logger.exception("Error getting coins data for WS request")
                        await ws.send_str(json.dumps({
                            "type": "coins_update",
                            "data": data,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }))

                elif msg.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                    break
        finally:
            self._ws_clients.discard(ws)
            logger.info("WebSocket client disconnected (%d remaining)", len(self._ws_clients))

        return ws

    # ------------------------------------------------------------------
    # Broadcast to all WebSocket clients
    # ------------------------------------------------------------------

    async def broadcast(self, event_type: str, data: dict[str, Any]) -> None:
        if not self._ws_clients:
            return
        message = json.dumps({
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        disconnected: set[web.WebSocketResponse] = set()
        for ws in self._ws_clients:
            try:
                await ws.send_str(message)
            except (ConnectionResetError, Exception):
                disconnected.add(ws)
        self._ws_clients -= disconnected

    # ------------------------------------------------------------------
    # Coin management API
    # ------------------------------------------------------------------

    async def _handle_get_coins(self, request: web.Request) -> web.Response:
        """GET /api/coins - All coins with market data and blacklist status."""
        coins: list[dict[str, Any]] = []
        if self._get_all_coins_data:
            try:
                coins = self._get_all_coins_data()
            except Exception:
                logger.exception("Error getting all coins data")
                return web.json_response({"error": "internal error"}, status=500)

        blacklisted = set()
        if self._coin_list_manager:
            blacklisted = self._coin_list_manager.get_blacklisted_coins()

        for coin in coins:
            coin["blacklisted"] = coin.get("coin", "") in blacklisted

        return web.json_response({"coins": coins, "total": len(coins)})

    async def _handle_get_blacklist(self, request: web.Request) -> web.Response:
        """GET /api/coins/blacklist - Current blacklist."""
        if not self._coin_list_manager:
            return web.json_response({"blacklist": []})
        return web.json_response({"blacklist": self._coin_list_manager.get_blacklist()})

    async def _handle_add_blacklist(self, request: web.Request) -> web.Response:
        """POST /api/coins/blacklist - Add coin to blacklist."""
        if not self._coin_list_manager:
            return web.json_response({"error": "coin list manager not configured"}, status=500)

        try:
            body = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response({"error": "invalid JSON"}, status=400)

        coin = body.get("coin", "").upper().strip()
        if not coin:
            return web.json_response({"error": "missing 'coin' field"}, status=400)

        reason = body.get("reason", "")
        added = await self._coin_list_manager.add_to_blacklist(coin, reason)
        if not added:
            return web.json_response({"error": f"{coin} is already blacklisted"}, status=409)

        return web.json_response({"success": True, "coin": coin, "reason": reason})

    async def _handle_remove_blacklist(self, request: web.Request) -> web.Response:
        """DELETE /api/coins/blacklist/{coin} - Remove coin from blacklist."""
        if not self._coin_list_manager:
            return web.json_response({"error": "coin list manager not configured"}, status=500)

        coin = request.match_info["coin"].upper().strip()
        removed = await self._coin_list_manager.remove_from_blacklist(coin)
        if not removed:
            return web.json_response({"error": f"{coin} is not in blacklist"}, status=404)

        return web.json_response({"success": True, "coin": coin})

    # ------------------------------------------------------------------
    # Frontend catch-all (serves React static pages)
    # ------------------------------------------------------------------

    async def _handle_frontend_fallback(self, request: web.Request) -> web.Response:
        """Serve React frontend pages and static files."""
        path = request.match_info.get("path", "").strip("/")

        # Try exact file match (favicon.ico, *.svg, etc.)
        exact = FRONTEND_BUILD_DIR / path
        if exact.is_file():
            return web.FileResponse(exact)

        # Try .html extension (/coins -> coins.html)
        html_file = FRONTEND_BUILD_DIR / f"{path}.html"
        if html_file.is_file():
            return web.FileResponse(html_file)

        # Try directory index (/coins/ -> coins/index.html)
        index_file = FRONTEND_BUILD_DIR / path / "index.html"
        if index_file.is_file():
            return web.FileResponse(index_file)

        # 404 page
        not_found = FRONTEND_BUILD_DIR / "404.html"
        if not_found.is_file():
            return web.FileResponse(not_found, status=404)

        return web.Response(text="Not found", status=404)

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
