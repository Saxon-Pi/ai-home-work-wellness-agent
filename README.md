# AI Home Work Wellness Agent

室内環境・天気・予定を統合的に判断し、  
LINE 上で健康アドバイスを行う AI Wellness Agent

---

## デモンストレーション

### LINE 上での AI アシスタント

📝TODO:
- LINE 会話スクリーンショットを貼る
- 「明日の朝の天気と予定を教えて」
- 「1日の CO2 濃度の推移は？」
などの会話例を掲載

---

### 室内環境レポート生成

📝TODO:
- CO2 / 温度 / 湿度グラフ画像を貼る
- AI による分析コメント付きの返信画面を掲載

---

### Agent の推論ログ

本システムでは、AI Agent が状況に応じて必要なツールを動的に選択している

```text
Tool #1: get_calendar_context_tool
Tool #2: get_weather_context_tool
Tool #3: generate_sensor_chart_report_tool
```

📝TODO:
- CloudWatch Logs のスクリーンショットを貼る
- 「ツールを推論で選択している」様子が分かる部分を切り取る

---

# システム概要

在宅ワークで仕事に集中していると、以下の要素に気づきにくい  
これらが原因で、仕事効率の低下や体調不良を引き起こす可能性がある  
- 換気不足（CO2濃度上昇）
- 温度 / 湿度の変化
- 過密スケジュール
- 天候の変化

本システムでは、以下の情報を AI Agent が統合的に判断し、  
ユーザに適切な行動提案を LINE 上で通知する  
これにより、作業効率の向上や適切な体調管理を促すことを目的としている  
- センサから得られた室内データ
- 天気情報
- Google Calendar

---

# 主な機能

- CO2 / 温度 / 湿度 モニタリング
- AI による健康アドバイス生成
- 天気情報との統合判断
- Google Calendar 連携
- センサデータのグラフ生成
- LINE Bot 通知
- AgentCore Gateway による MCP Tool 管理

---

# システムアーキテクチャ

📝TODO:
- システム全体図を貼る
- 以下を含めると良い
  - Raspberry Pi + SCD40
  - AWS IoT Core
  - DynamoDB / Athena
  - Lambda
  - Bedrock
  - AgentCore Gateway
  - LINE Bot
  - Grafana

---

# AI Agent アーキテクチャ

本システムでは、Strands Agents を利用して  
複数ツールを推論ベースで動的選択する AI Agent を構築している  

Agent は以下の情報を統合して判断する  
- 室内環境
- 天気
- スケジュール
- 時間帯
- センサデータ推移

---

## MCP / AgentCore Gateway によるツール管理

ツール実行は AgentCore Gateway + MCP protocol に統一している

これにより、以下を実現した構成としている
- Agent 側からツール実装を疎結合化
- Lambda / ECS / 外部 API を統一的に扱う
- schema ベースでツールを動的認識
- ツール追加時の Agent 修正を最小化

📝TODO:
- MCP / AgentCore Gateway の構成図を貼る
- 「Agent ⇔ Gateway ⇔ Lambda Tool」の流れを図示

---

# 技術的な工夫ポイント

## 1. 推論ベースの Tool Selection

単純な Function Calling ではなく、  
AI Agent が状況に応じて必要なツールを判断している  

例:  

- 「明日の朝の天気と予定を教えて」
  - Calendar Tool
  - Weather Tool

- 「1日の CO2 推移を見せて」
  - Report Generation Tool

---

## 2. MCP ベースの疎結合アーキテクチャ

ツール実行を MCP protocol に統一し、  
AgentCore Gateway から tool schema を取得する構成としている  

これにより、以下を実現している　　
- ツール実装の分離
- 実行環境の抽象化
- 将来的な Runtime 移行
- サーバレス MCP 構成

---

## 3. サーバレス構成

本システムは Lambda + AgentCore Gateway により、  
MCP ベースのツールアーキテクチャをサーバレスで実現している　　

従来の MCP Server のように ECS などの常駐サーバを必要とせず、  
AWS マネージドな構成で動作する  

---

## 4. コンテキスト統合理解

単なるセンサ監視ではなく、以下の情報を横断的に判断し、  
ユーザー行動に合わせた自然なアドバイスを生成する  
- 室内環境
- 天気
- スケジュール
- 時間帯

---

# 使用技術

| 技術 | 用途 |
|---|---|
| AWS Lambda | Agent / Tool 実行 |
| Amazon Bedrock | LLM |
| Strands Agents | AI Agent Framework |
| AgentCore Gateway | MCP Tool 管理 |
| MCP protocol | Tool 標準化 |
| AWS IoT Core | MQTT ingestion |
| DynamoDB | センサーデータ保存 |
| Athena | データ分析 |
| Grafana | 可視化 |
| LINE Messaging API | ユーザー通知 |
| Raspberry Pi | センサーデバイス |
| SCD40 | CO2 / 温湿度センサ |

---

# セットアップ手順

詳細なセットアップ手順は docs 配下を参照

| ドキュメント | 内容 |
|---|---|
| [00_システム構想メモ.md](./docs/00_システム構想メモ.md) | 全体構想 |
| [01_SCD40接続・MQTT送信手順書.md](./docs/01_SCD40接続・MQTT送信手順書.md) | センサ構築 |
| [02_IoTCore-ラズパイ接続手順書.md](./docs/02_IoTCore-ラズパイ接続手順書.md) | IoT Core 接続 |
| [03_Grafanaデータ可視化手順書.md](./docs/03_Grafanaデータ可視化手順書.md) | Grafana |
| [04_StrandsAgent化構想メモ.md](./docs/04_StrandsAgent化構想メモ.md) | Agent 化 |
| [05_ツールMCP化構想メモ.md](./docs/05_ツールMCP化構想メモ.md) | MCP 化 |
| [06_AgentCore化構想メモ.md](./docs/06_AgentCore化構想メモ.md) | AgentCore Gateway 化 |

---

# 今後の改善

- AgentCore Runtime への移行
- Memory によるユーザー行動学習
- Observability 強化
- マルチ Agent 化
- 長期行動分析

---

# License

MIT
