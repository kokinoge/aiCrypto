"""メインネット / テストネット両方の残高を確認するスクリプト"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from hyperliquid.info import Info
from hyperliquid.utils import constants
from src.utils.logger import setup_logger


def check(name: str, url: str, address: str):
    try:
        info = Info(url, skip_ws=True)
        state = info.user_state(address)
        summary = state["marginSummary"]
        equity = float(summary["accountValue"])
        print(f"  {name}: ${equity:,.2f}")
    except Exception as e:
        print(f"  {name}: Error - {e}")


def main():
    setup_logger(level="WARNING")

    addresses = {
        "新アドレス": "0x1969E89a3DF36A26E78d804FfAa6863ABFaa92ca",
        "旧アドレス": "0xfaae3D9D3DBd37539bFA7D8aE1c87f73D7345db8",
    }

    for label, addr in addresses.items():
        print(f"\n{label}: {addr}")
        check("TESTNET", constants.TESTNET_API_URL, addr)
        check("MAINNET", constants.MAINNET_API_URL, addr)


if __name__ == "__main__":
    main()
