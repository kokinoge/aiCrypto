from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


@dataclass
class RiskConfig:
    max_risk_per_trade_pct: float = 3.0
    stop_loss_pct: float = 5.0
    take_profit_pct: float = 10.0
    max_positions: int = 3
    max_drawdown_pct: float = 20.0
    max_leverage: int = 3


@dataclass
class SignalConfig:
    min_confidence: float = 0.6
    cooldown_minutes: int = 30


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/bot.log"


@dataclass
class BotConfig:
    mode: str = "paper"  # "paper", "testnet", or "mainnet"
    risk: RiskConfig = field(default_factory=RiskConfig)
    signals: SignalConfig = field(default_factory=SignalConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    trading_pairs: list[str] = field(default_factory=list)
    paper_trading_balance: float = 1000.0

    # Webhook server
    webhook_enabled: bool = True
    webhook_port: int = 8080

    # Secrets from environment
    hl_secret_key: str = ""
    hl_account_address: str = ""
    discord_bot_token: str = ""
    discord_nansen_channel_id: int = 0
    discord_notify_channel_id: int = 0
    nansen_api_key: str = ""
    anthropic_api_key: str = ""

    @property
    def is_testnet(self) -> bool:
        return self.mode == "testnet"

    @property
    def is_paper(self) -> bool:
        return self.mode == "paper"


def load_config(path: Path | None = None) -> BotConfig:
    path = path or CONFIG_PATH

    raw: dict = {}
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

    risk = RiskConfig(**raw.get("risk", {}))
    signals = SignalConfig(**raw.get("signals", {}))
    log_cfg = LoggingConfig(**raw.get("logging", {}))

    webhook_raw = raw.get("webhook", {})

    return BotConfig(
        mode=raw.get("mode", "paper"),
        risk=risk,
        signals=signals,
        logging=log_cfg,
        trading_pairs=raw.get("trading_pairs", []),
        paper_trading_balance=raw.get("paper_trading_balance", 1000.0),
        webhook_enabled=webhook_raw.get("enabled", True),
        webhook_port=webhook_raw.get("port", 8080),
        hl_secret_key=os.getenv("HL_SECRET_KEY", "").strip(),
        hl_account_address=os.getenv("HL_ACCOUNT_ADDRESS", "").strip(),
        discord_bot_token=os.getenv("DISCORD_BOT_TOKEN", "").strip().strip('"').strip("'"),
        discord_nansen_channel_id=int(os.getenv("DISCORD_NANSEN_CHANNEL_ID", "0").strip()),
        discord_notify_channel_id=int(os.getenv("DISCORD_NOTIFY_CHANNEL_ID", "0").strip()),
        nansen_api_key=os.getenv("NANSEN_API_KEY", "").strip(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
    )
