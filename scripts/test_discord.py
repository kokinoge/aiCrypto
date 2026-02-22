"""
Discord Bot 接続確認スクリプト

使い方:
  python -m scripts.test_discord

Botがサーバーに接続できるか、チャンネルが見つかるかを確認する。
確認後、自動的に切断する。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import discord
from src.config import load_config
from src.utils.logger import setup_logger


async def main():
    logger = setup_logger(level="INFO")
    config = load_config()

    if not config.discord_bot_token:
        logger.error("DISCORD_BOT_TOKEN が .env に設定されていません")
        return

    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        logger.info("Discord Bot 接続成功: %s", client.user)
        logger.info("参加サーバー数: %d", len(client.guilds))

        for guild in client.guilds:
            logger.info("  サーバー: %s", guild.name)

        nansen_ch = client.get_channel(config.discord_nansen_channel_id)
        if nansen_ch:
            logger.info("nansen-alerts チャンネル: OK (#%s)", nansen_ch.name)
        else:
            logger.error("nansen-alerts チャンネル: 見つからない (ID: %d)", config.discord_nansen_channel_id)

        notify_ch = client.get_channel(config.discord_notify_channel_id)
        if notify_ch:
            logger.info("bot-trades チャンネル: OK (#%s)", notify_ch.name)
            await notify_ch.send("Trading Bot 接続テスト成功！")
            logger.info("テストメッセージを送信しました")
        else:
            logger.error("bot-trades チャンネル: 見つからない (ID: %d)", config.discord_notify_channel_id)

        logger.info("=== Discord テスト完了 ===")
        await client.close()

    try:
        await client.start(config.discord_bot_token)
    except discord.LoginFailure:
        logger.error("Discord ログイン失敗: Botトークンが正しくない可能性があります")
    except Exception as e:
        logger.error("Discord接続エラー: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
