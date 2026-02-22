# Smart Money Trading Bot

Nansen Smart AlertsのDiscord通知を監視し、Hyperliquid DEXで自動取引を行うBot。

## セットアップ

### 1. Python環境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. 設定ファイル

```bash
cp config.example.yaml config.yaml
```

`config.yaml` を編集してリスク管理パラメータを調整。

### 3. 環境変数

`.env` ファイルを作成:

```
HL_SECRET_KEY=0x_your_private_key
HL_ACCOUNT_ADDRESS=0x_your_address
DISCORD_BOT_TOKEN=your_bot_token
DISCORD_NANSEN_CHANNEL_ID=123456789
DISCORD_NOTIFY_CHANNEL_ID=123456789
```

### 4. テスト

```bash
# マーケットデータ接続テスト（API不要）
python -m scripts.test_connection

# シグナル解析テスト（API不要）
python -m scripts.test_signal
```

### 5. 起動

```bash
python -m src.main
```

## 動作フロー

1. Nansen Smart AlertsがDiscordチャンネルに通知を送る
2. Botがメッセージを解析し、売買シグナルを判定
3. リスク管理チェック後、Hyperliquidで注文を実行
4. 取引結果をDiscordに通知

## リスク管理

- 1取引の最大リスク: 資金の3%（デフォルト）
- ストップロス / テイクプロフィット自動設定
- 最大同時ポジション: 3
- 最大ドローダウン20%でBot自動停止
