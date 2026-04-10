# 在宅ワーク健康支援AIエージェント（ai-home-work-wellness-agent）

## 欲望
- AI Agent システムを作りつつ学びたい
- Strands SDK / AgentCore を使って開発したい
- IoT Core 使いたい
- 電子工作したい
- Timestream 使いたい（Grafanaで可視化したい）
    → Timestream for LiveAnalytics が 25 年 6 月でアクセス終了のため代替案検討
- LINE と連携させたい
- いい感じのアーキ図描きたい
- どうせ作るなら役に立つものを実用レベルまで仕上げる

---

## コンセプト
- AI エージェント + IoT センサー + 生活の役に立つ何か  
**👉 在宅ワーク健康支援AIエージェント**

--- 

## MVP 機能

### MVP
- センサーデータを IoT Core 経由でAWSへ送る
- Timestream に保存
- 定期的に Agent が状況判定
- LINE に提案通知

### 提案内容
- 換気
- 水分補給
- 短いストレッチ
- 散歩提案（天気と予定が合えば）
    - 天気情報取得API、Googleカレンダー連携

--- 

## MVP 構成
```mermaid
flowchart TD

A[温度 / 湿度 / CO2 センサー<br>Raspberry Pi] --> B[AWS IoT Core]
B --> C[IoT Rule]
C --> D[Lambda<br>データ整形 / 保存]
D --> E[Amazon Timestream]

F[EventBridge Scheduler<br>定期起動] --> G[Wellness Agent]
E --> G
H[天気API] --> G
I[Google Calendar] --> G

G --> J[Amazon Bedrock]
G --> K[LINE Messaging API]
K --> L[ユーザー]
```

---

## ハード
IoT Core で扱いやすいハードが望ましい

### ⭕️ Raspberry Pi + センサー
- Python との相性が良い
- AWS IoT Core に繋ぎやすい
- 拡張しやすい（カメラやマイク・スピーカーなど）
- Agent 側のローカル前処理がやりやすい

### 🔺 Arduino系 + センサー
- マイコン側の実装あり
- 開発・デバッグの難易度が上がる
- AWS接続も工夫が必要になる

### ❌ 既製品の Wi-Fi 温湿度計
- データ連携のしやすさは機種によりけり
- AWS IoT Core と直接つなぎにくい
- 「自分で作った感」が減る🥺

--- 

## センサー

### CO2 センサー
- CO2 高い → 換気 の提案
- SCD40 / SCD41 / MH-Z19C
    - https://akizukidenshi.com/catalog/g/g117851/
    - ⬆️ なら CO2 に加えて、温度、湿度も測定できる
    - 高精度（±50ppm + 5%）、ラズパイと接続可

### 温湿度センサー
- 温度高い → 室温調整 / 水分補給 の提案
- 湿度低い → 乾燥対策 の提案
- BME280 / SHT31
    - https://akizukidenshi.com/catalog/g/g109421/

---

## IoT Core 採用理由
センサー値を API Gateway に POST する構成にすることも可能だが、
以下の点で IoT Core を採用する
- IoT 向けの接続方式が最初から揃っている（実装が楽）
    - デバイス認証
	- MQTT 通信
	- topic ベース配信
	- ルールエンジン

- デバイス証明書ベースで安全
    - デバイスごとに証明書を持たせて接続できる

- MQTT が使用できる
    - 軽量で小さいデータを送りやすい
    - 常時接続がしやすい
    - pub/sub と相性が良い

- pub/sub が使える
    - **双方向性や拡張性が高い**
        - AI がセンサーデータを取得するだけでなく、デバイスの操作もできるようになる
        - AI に写真を撮影させたり、エアコンをONにしてもらうことも可能
    - デバイス: publish
    - 接続先: subscribe

- IoT Rule が便利
    - メッセージをどこに流すかルール定義が可能
        - Timestream に保存
	    - Lambda を起動
	    - DynamoDB に保存
        - etc...

---

### IoT Core ペイロードイメージ
ラズパイ → IoT Core には以下の形式でデータを送信する  
トピック：wellness/device/raspi-home-1/telemetry

```json
{
  "device_id": "raspi-home-1",
  "timestamp": "2026-04-01T09:00:00Z",
  "temperature": 28.1,
  "humidity": 42.3,
  "co2_ppm": 1320
}
```

---

## LINE連携
Slack 通知は散々やってるので LINE を使いたい  
モバイル連携向けな点も👌

### Push通知（イメージ）
「CO2 が高めです。次の会議まで15分あるので、今のうちに5分だけ換気しませんか？」

### 質問応答
ユーザー:  
「今の部屋の状態どう？」  
  
Agent:  
「現在 CO2 は 1380ppm で高めです。室温は 28.1℃ です。  
今日は 90分以上座りっぱなしなので、短い休憩と換気をおすすめします。」  

---

## Strands Agent化の方針
今まで作成してきたシステムを Strandsの「ツールを使うAgent化」にバージョンアップする  
Strands Agent化することにより、現在Lambda一本で運用していたシステムが、以下のように役割分担される  
- Lambda は起動担当
- Agent は判断担当
- ツールはデータ取得担当

### アーキテクチャイメージ
```mermaid
flowchart LR
    EB[EventBridge<br/>定期実行] --> WL[WellnessAgentLambda]

    WL --> SA[Strands Agent]

    SA --> T1[get_environment_summary<br/>DynamoDBから直近データ取得・集計]
    SA --> T2[get_calendar_events<br/>Google Calendar API]
    SA --> T3[get_weather_summary<br/>Weather API]
    SA --> T4[send_line_message<br/>LINE Messaging API]

    T1 --> DDB[(DynamoDB<br/>room_metrics)]
    T2 --> GC[Google Calendar]
    T3 --> WA[Weather API]
    T4 --> LINE[LINE]

    SA --> BR[Amazon Bedrock]
```

### 作業ステップ
Strands Agent化するにあたり、以下のステップで進ていく

### 既存のLambda関数をツール化
Strands Agentがツールを使ってセンサデータのサマリを取得し、それに基づく最終的な回答を生成させる
ツール化する関数の候補は以下
- get_environment_summary: 室内環境情報を取得
    - get_recent_sensor_data: デバイスから送られてきた室内環境データを取得
    - summarize_sensor_data: 室内環境データの前処理
    - classify_environment: 最新データから室内環境ステータスを分類
- send_line_message: LINEにメッセージを送信
- get_current_time_context: 現在時刻や時間帯を取得

### 外部コンテキスト追加
Agentに外部APIを使用した情報収集をさせる
- get_calendar_events: Googleカレンダーのスケジュールに沿ったタイミングや内容の回答を生成させる
- get_weather_summary: 天気予報の結果を取得

### コミュニケーションの双方向化
- ユーザがLINEで現在の状態や推奨アクションの問い合わせができるようにする

### AgentCore
- Strands Agent を AgentCore 上で動作させることで、実行基盤・認証・メモリ・観測性などを含む本番運用寄りの構成を体験する
