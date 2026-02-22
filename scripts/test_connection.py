"""
Hyperliquid テストネット接続確認スクリプト

使い方:
  python -m scripts.test_connection

秘密鍵がなくても実行可能（マーケットデータの取得だけ確認する）。
.env に HL_SECRET_KEY と HL_ACCOUNT_ADDRESS を設定すれば
アカウント情報も取得できる。
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config
from src.hyperliquid.client import HyperliquidClient
from src.utils.logger import setup_logger


def main():
    logger = setup_logger(level="INFO")
    config = load_config()

    # Force testnet for safety
    config.mode = "testnet"
    logger.info("Connecting to Hyperliquid TESTNET...")

    client = HyperliquidClient(config)

    # 1. Get tradeable coins
    logger.info("--- Tradeable Coins ---")
    coins = client.get_tradeable_coins()
    logger.info("Found %d coins: %s", len(coins), ", ".join(coins[:20]) + ("..." if len(coins) > 20 else ""))

    # 2. Get market info for BTC and ETH
    for coin in ["BTC", "ETH"]:
        logger.info("--- %s Market Info ---", coin)
        try:
            info = client.get_market_info(coin)
            logger.info("  Mark Price:    $%s", f"{info.mark_price:,.2f}")
            logger.info("  Funding Rate:  %s%%", f"{info.funding_rate * 100:.4f}")
            logger.info("  Open Interest: %s", f"{info.open_interest:,.2f}")
        except Exception as e:
            logger.error("  Failed: %s", e)

    # 3. Get account state (requires HL_ACCOUNT_ADDRESS)
    if config.hl_account_address:
        logger.info("--- Account State ---")
        try:
            state = client.get_account_state()
            logger.info("  Equity:    $%s", f"{state.equity:,.2f}")
            logger.info("  Available: $%s", f"{state.available_balance:,.2f}")
            logger.info("  Positions: %d", len(state.positions))
            for pos in state.positions:
                logger.info(
                    "    %s %s | size=%.6f | entry=$%.2f | pnl=$%.2f",
                    pos.side.upper(), pos.coin, pos.size, pos.entry_price, pos.unrealized_pnl,
                )
        except Exception as e:
            logger.error("  Failed: %s", e)
    else:
        logger.info("--- Account State ---")
        logger.info("  Skipped (HL_ACCOUNT_ADDRESS not set in .env)")

    logger.info("=== Connection test complete ===")


if __name__ == "__main__":
    main()
