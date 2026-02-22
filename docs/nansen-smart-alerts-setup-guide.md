# Nansen Smart Alerts × Discord 設定ガイド

> このガイドは、Nansenの無料アカウントを使ってSmart Alertsを設定し、Discordチャンネルに通知を送るための手順書です。コードの知識は不要です。

---

## 目次

1. [プランの確認（無料プランでできること）](#1-プランの確認)
2. [Discordサーバーの準備](#2-discordサーバーの準備)
3. [Discord Webhookの作成](#3-discord-webhookの作成)
4. [Nansen Smart Alertsの設定](#4-nansen-smart-alertsの設定)
5. [アラートの種類と選び方](#5-アラートの種類と選び方)
6. [Discordに届くメッセージの形式](#6-discordに届くメッセージの形式)
7. [トラブルシューティング](#7-トラブルシューティング)

---

## 1. プランの確認

### Nansenの料金プラン（2026年2月時点）

| プラン | 月額 | Smart Alerts | 主な違い |
|--------|------|-------------|----------|
| **Free** | $0 | 基本的なオンチェーンシグナル | 基本的なウォレット分析、AI Smart Search |
| **Pioneer** | $99/月 | 全シグナル＋フィルター機能 | Nansenラベル（3億以上のアドレス）、高度な分析 |
| **Professional** | $999/月 | 全機能＋無制限カスタマイズ | CSV出力、専任サポート |

### 無料プランでSmart Alertsは使えるか？

**はい、使えます。** 無料プランでも「基本的なオンチェーンシグナル」としてSmart Alerts機能にアクセスできます。ただし、以下の制限がある可能性があります：

- 設定できるアラートの数に上限がある
- フィルター機能（シグナルの詳細な絞り込み）はPioneer以上
- 「Smart Money」ラベルを使った高度なアラートはPioneer以上で利用可能

**推奨**: まずは無料プランで試してみて、足りないと感じたらPioneer（$99/月）へのアップグレードを検討してください。

### プランの確認・変更方法

1. https://app.nansen.ai/account にアクセス
2. 「Change Plan」をクリック
3. 比較表で各プランの詳細を確認: https://app.nansen.ai/account/switch-plans

---

## 2. Discordサーバーの準備

### まだサーバーがない場合

1. Discord デスクトップアプリをダウンロード: https://discord.com/download
2. Discordを起動してログイン
3. 左側の「＋」ボタンをクリック
4. 「オリジナルの作成」を選択
5. サーバー名を入力（例: 「Nansen Alerts」）
6. 「新規作成」をクリック

### チャンネルの作成

Bot用に**2つのチャンネル**を作ることを推奨します：

1. **#nansen-alerts** — Nansenからのアラートが届くチャンネル
2. **#trading-notify** — Botの取引通知用チャンネル

**チャンネルの作り方:**
1. サーバー名の横にある「＋」（チャンネルを追加）をクリック
2. 「テキストチャンネル」を選択
3. チャンネル名を入力（例: `nansen-alerts`）
4. 「チャンネルを作成」をクリック

---

## 3. Discord Webhookの作成

Webhookとは、外部サービス（Nansen）がDiscordチャンネルにメッセージを自動送信するための仕組みです。

### 手順

1. Discordを開く
2. 左側のサーバーアイコンを **右クリック**
3. 「**サーバー設定**」を選択
4. 左メニューから「**連携サービス**」（Integrations）をクリック
5. 「**Webhookを表示**」（View Webhooks）をクリック
6. 「**新しいWebhook**」をクリック
7. 以下を設定：
   - **名前**: `Nansen Smart Alerts`（任意）
   - **チャンネル**: 先ほど作成した `#nansen-alerts` を選択
8. 「**Webhook URLをコピー**」ボタンをクリック
9. コピーしたURLをメモ帳などに一時保存

> **重要**: Webhook URLは外部に漏らさないでください。このURLを知っている人は誰でもチャンネルにメッセージを送れます。

### Webhook URLの形式

コピーしたURLは以下のような形式です：

```
https://discord.com/api/webhooks/1234567890/ABCDEFghijklmnop...
```

---

## 4. Nansen Smart Alertsの設定

### 方法A: AI Smart Alerts（推奨・最も簡単）

2025年7月以降、NansenにはAIが自動でアラートを作成する機能が追加されました。

1. https://app.nansen.ai/smart-alerts にアクセス
2. 「**Add New Alert**」（新しいアラートを追加）をクリック
3. **テキストボックスに日本語または英語でやりたいことを入力**

   入力例:
   - `Smart Money wallets buying ETH or SOL worth more than $100,000`
   - `Large exchange inflows of any token above $500,000`
   - `Whale wallets accumulating new tokens`

4. AIがアラートの設定を自動生成するのを待つ
5. 内容を確認して「**Create Alert**」をクリック
6. 通知先の設定で「**Discord**」を選択
7. 手順3でコピーした **Webhook URL** を貼り付け
8. 「**Save**」（保存）をクリック

### 方法B: Simple Alerts（手動・30秒で作成）

特定のアドレスを監視したい場合はこちら。

1. https://app.nansen.ai/smart-alerts にアクセス
2. 「**Add New Alert**」をクリック
3. 「**Simple Alerts**」を選択
4. 以下を設定:
   - **Chain**（チェーン）: Ethereum、Solana などを選択
   - **Address**（アドレス）: 監視したいウォレットアドレスを入力または選択
   - **Minimum Value**（最小取引額）: 通知するトランザクションの最低金額を設定
   - **Exclusions**（除外）: ステーブルコイン、ネイティブトークンなどを除外可能
5. 通知先で「**Discord**」を選択
6. Webhook URLを貼り付け
7. 保存

### 方法C: Advanced Alerts（上級者向け）

より複雑な条件設定が可能。

1. https://app.nansen.ai/smart-alerts にアクセス
2. 「**Add New Alert**」→「**Advanced Alerts**」を選択
3. アラートタイプを選択（後述の「アラートの種類」を参照）
4. 詳細なフィルターを設定
5. 通知先で「Discord」を選択
6. Webhook URLを貼り付けて保存

---

## 5. アラートの種類と選び方

### 利用可能なアラートタイプ

| アラートタイプ | 内容 | Bot取引との相性 |
|---------------|------|----------------|
| **Token Transfer**（トークン送金） | 特定トークンの大口送金を検知 | ★★★ |
| **Smart Money Token Flow**（Smart Moneyフロー） | Smart Moneyウォレットのトークン流入・流出を検知 | ★★★★★ |
| **Exchange Flow**（取引所フロー） | 取引所への大口入出金を検知 | ★★★★ |
| **Token/NFT Signals**（シグナル） | オンチェーン活動の異常なスパイクを検知 | ★★★★ |
| **Hot Contracts**（人気コントラクト） | 急にアクセスが増えたスマートコントラクトを検知 | ★★★ |
| **NFT Transfer**（NFT送金） | NFTコレクションの大口取引を検知 | ★ |

### 自動取引Botに推奨するアラート設定

このプロジェクトのBotと連携する場合、以下の設定がおすすめです：

#### 1. Smart Money Token Flow（最優先）
- **何が分かる**: 優秀なトレーダー（Smart Money）がどのトークンを買っている/売っているか
- **設定例**: Smart Moneyウォレットのトークン流入、最小金額$100,000以上
- **Botが検知するキーワード**: `buying`, `bought`, `accumulated`, `inflow`, `smart money`

#### 2. Exchange Flow（取引所フロー）
- **何が分かる**: 大量のトークンが取引所に送られている（売り圧力の兆候）
- **設定例**: Ethereum上の全トークン、最小金額$500,000以上
- **Botが検知するキーワード**: `inflow`（売りシグナル）, `outflow`（買いシグナル）

#### 3. Token Signals（トークンシグナル）
- **何が分かる**: 異常なオンチェーン活動の急増
- **設定例**: 時価総額上位100トークン対象
- **Botが検知するキーワード**: `bullish`, `bearish`, `whale`

### 対応チェーン

Smart Alertsは以下のチェーンに対応しています：

Ethereum, Polygon, BNB Chain, Arbitrum, Avalanche, Fantom, Base, Linea, Blast, Optimism, Mantle, ZKsync

---

## 6. Discordに届くメッセージの形式

NansenからDiscord Webhookに送信されるメッセージは、Discord Embed形式で届きます。

### メッセージの構造

Nansenのアラートメッセージには通常、以下の情報が含まれます：

```
[Embed]
Title:    Smart Money Token Flow Alert
Description: Smart Money wallet bought 500,000 USDC worth of ETH
Fields:
  - Token:     ETH (Ethereum)
  - Direction: Inflow / Bought
  - Amount:    $500,000
  - Wallet:    0x1234...abcd (Labeled: Smart Money)
  - Chain:     Ethereum
  - Tx Hash:   0xabcd...1234
```

### Botが解析する情報

このプロジェクトのBot（`src/signals/engine.py`）は、以下を自動解析します：

1. **コイン名の検出**: メッセージ内の `ETH`, `BTC`, `SOL` などのティッカーシンボル、または `Ethereum`, `Bitcoin` などのフルネーム
2. **売買方向の判定**: 以下のキーワードで判定
   - **買い（Long）**: `buying`, `bought`, `accumulated`, `inflow`, `adding`, `bullish`
   - **売り（Short）**: `selling`, `sold`, `dumping`, `outflow`, `removing`, `bearish`
3. **信頼度の加算**:
   - `smart money` というキーワードがあると信頼度 +20%
   - `whale` というキーワードがあると信頼度 +15%
   - `fund` というキーワードがあると信頼度 +20%

### Botとの連携を最適化するアラート設定のコツ

- アラートの説明文に**トークンのティッカーシンボル**（ETH, BTC, SOL等）が含まれるアラートを選ぶ
- **買い/売りの方向**が明示されるアラートタイプを選ぶ（Token Flow、Exchange Flow）
- **Smart Money**や**Whale**に関連するアラートを選ぶと信頼度が高く判定される
- 金額のしきい値を十分に高く設定し、ノイズを減らす（$100,000以上推奨）

---

## 7. トラブルシューティング

### アラートがDiscordに届かない

1. **Webhook URLを確認**: Nansenの設定画面でURLが正しく貼り付けられているか確認
2. **チャンネルの権限**: Webhookが正しいチャンネルに設定されているか確認
3. **Discordサーバーの権限**: 「連携サービス」の管理権限があるか確認
4. **アラートが有効か確認**: NansenのダッシュボードでアラートのトグルがONになっているか確認

### Webhook URLのテスト

ターミナル（端末）を使える場合、以下のコマンドでWebhookの動作を確認できます：

```bash
curl -H "Content-Type: application/json" \
  -d '{"content": "Nansen Webhook テスト成功！"}' \
  "あなたのWebhook URL"
```

成功すると、Discordチャンネルに「Nansen Webhook テスト成功！」と表示されます。

### Botがシグナルを検出しない

- Botが監視しているチャンネルID（`DISCORD_NANSEN_CHANNEL_ID`）が正しいか確認
- アラートのメッセージにトークン名が含まれているか確認
- 買い/売りキーワードがメッセージに含まれているか確認
- `config.yaml` の `trading_pairs` に対象トークンが含まれているか確認

---

## 参考リンク

| リンク | 内容 |
|--------|------|
| https://app.nansen.ai/smart-alerts | Smart Alerts ダッシュボード |
| https://app.nansen.ai/account/switch-plans | プラン比較・変更 |
| https://academy.nansen.ai/articles/6239622-ai-smart-alerts-101 | AI Smart Alerts 公式ガイド |
| https://www.nansen.ai/guides/smart-alerts-the-ultimate-crypto-alerts-for-traders | Smart Alerts 詳細ガイド |
| https://www.nansen.ai/plans | 料金プラン |
| https://discord.com/download | Discord ダウンロード |

---

## まとめ: 設定の全体フロー

```
1. Nansen無料アカウントでログイン
   https://app.nansen.ai

2. Discordでサーバーを作成し、#nansen-alerts チャンネルを作る

3. サーバー設定 → 連携サービス → Webhook作成 → URLコピー

4. Nansen Smart Alerts ページで新しいアラートを追加
   https://app.nansen.ai/smart-alerts

5. AIに「Smart Money buying ETH」のように入力、またはSimple/Advancedで手動設定

6. 通知先にDiscordを選択 → Webhook URLを貼り付け → 保存

7. アラートがDiscordチャンネルに届くのを確認

8. BotがDiscordチャンネルを監視して自動取引を実行
```
