"""
ペーパートレードの動作テスト

使い方:
  python -m scripts.test_paper_trade

実際のHyperliquid価格を使って、仮想的に売買する。
お金は一切使わない。
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import load_config
from src.hyperliquid.client import HyperliquidClient
from src.hyperliquid.paper_trader import PaperTrader, PAPER_STATE_FILE
from src.hyperliquid.risk import RiskManager
from src.utils.logger import setup_logger


def main():
    logger = setup_logger(level="INFO")
    config = load_config()
    config.mode = "paper"
    config.paper_trading_balance = 1000.0

    # Reset portfolio for clean test
    if PAPER_STATE_FILE.exists():
        PAPER_STATE_FILE.unlink()

    client = HyperliquidClient(config)
    risk = RiskManager(config, client)
    paper = PaperTrader(config, client, risk)

    logger.info("=" * 50)
    logger.info("Paper Trading Test")
    logger.info("=" * 50)

    # Show initial state
    summary = paper.get_summary()
    logger.info("Initial balance: $%.2f", summary["equity"])

    # Simulate signals
    test_signals = [
        ("BTC", "long", 0.8),
        ("ETH", "short", 0.7),
        ("SOL", "long", 0.9),
        ("DOGE", "long", 0.6),  # Should be blocked (max 3 positions)
    ]

    for coin, side, confidence in test_signals:
        logger.info("--- Signal: %s %s (confidence=%.1f) ---", side.upper(), coin, confidence)
        result = paper.execute_signal(coin, side, confidence)
        if result and result.success:
            logger.info("  -> Trade executed!")
        elif result:
            logger.info("  -> Blocked: %s", result.error)
        else:
            logger.info("  -> Skipped")

    # Show final state
    logger.info("")
    logger.info("=" * 50)
    logger.info("Portfolio Summary")
    logger.info("=" * 50)
    summary = paper.get_summary()
    logger.info("Equity:        $%.2f", summary["equity"])
    logger.info("Cash:          $%.2f", summary["cash"])
    logger.info("Total PnL:     $%.2f", summary["total_pnl"])
    logger.info("Return:        %.1f%%", summary["return_pct"])
    logger.info("Open Positions: %d", summary["open_positions"])

    for pos in summary["positions"]:
        logger.info(
            "  %s %s | entry=$%.2f | pnl=$%.2f",
            pos.side.upper(), pos.coin, pos.entry_price, pos.unrealized_pnl,
        )

    # Test close all
    logger.info("")
    logger.info("--- Closing all positions ---")
    results = paper.close_all_positions()
    for r in results:
        logger.info("  Closed %s at $%.2f", r.coin, r.price)

    summary = paper.get_summary()
    logger.info("Final equity: $%.2f | PnL: $%.2f", summary["equity"], summary["total_pnl"])
    logger.info("=== Test complete ===")


if __name__ == "__main__":
    main()
