"""
シグナルエンジンのテストスクリプト

使い方:
  python -m scripts.test_signal

Nansen Smart Alertのサンプルメッセージでシグナル解析をテストする。
外部API不要。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.signals.engine import SignalEngine
from src.utils.logger import setup_logger


SAMPLE_ALERTS = [
    "Smart Money is accumulating $ETH — 5 funds added to their positions in the last 24h",
    "Whale alert: Large $BTC selling detected, smart trader dumping 500 BTC on Hyperliquid",
    "Smart Money inflows into $SOL have increased by 340% over the past 7 days",
    "Fund outflows detected for $DOGE — 3 smart traders removed their positions",
    "New token listing alert: $XYZ launched on Uniswap",
    "$ARB Smart Money buying pressure — 12 funds bought in the last 6 hours, bullish sentiment",
    "Random message with no trading relevance whatsoever",
]


def main():
    logger = setup_logger(level="DEBUG")
    engine = SignalEngine()

    logger.info("=== Signal Engine Test ===\n")

    for i, msg in enumerate(SAMPLE_ALERTS, 1):
        logger.info("--- Test %d ---", i)
        logger.info("Message: %s", msg)
        signal = engine.parse_alert(msg)
        if signal:
            logger.info(
                "  -> SIGNAL: %s %s | confidence=%.2f",
                signal.side.upper(), signal.coin, signal.confidence,
            )
        else:
            logger.info("  -> No signal")
        print()

    logger.info("=== Test complete ===")


if __name__ == "__main__":
    main()
