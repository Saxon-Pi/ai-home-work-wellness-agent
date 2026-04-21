"""
Chat Agent が室内環境、カレンダー、天気情報の取得と、LINE 返信を行うために使用するツール群
これらのツールは、LINE Webhook から起動される Chat Agent から利用されることを想定している

Agent はこれらのツールを使い、以下の流れで動作する
- 現在の室内環境を確認
- 今後の予定を確認
- 現在の天気や気象リスクを確認
- 上記に関する質問の回答を生成
- 最終的な返答を LINE に送信
"""

from typing import Any, Dict
from strands import tool

# 既存の Lambda 関数から関数をインポート
# Lambda Layer から core.py を読み込む
from common.core import (
    DEVICE_ID,        # デバイスID
    LOOKBACK_MINUTES, # データ取得期間 (デフォルトは1時間)
    # 直近1時間の室内環境サマリを取得する関数 (最新値、平均値、最大値、CO2トレンド、環境ステータス)
    get_environment_summary,
    # Google Calendar 連携用関数
    get_calendar_context,
    # 天気予報連携用関数
    get_weather_context,
    # LINE のチャットに応答する関数
    reply_line_message,
)

# 直近1時間の室内環境データを取得し、要約した結果を返すツール
@tool
def get_environment_summary_tool() -> Dict[str, Any]:
    """
    直近1時間の室内環境データを取得するツールです。
    室内環境に関する質問の回答やアドバイスをする際に使用してください。
    
    以下の情報を返します:
    - summary:
        - latest: 最新の CO2濃度、温度、湿度
        - avg_1h: 直近1時間の平均値
        - max_1h: 直近1時間の最大値
        - co2_trend: CO2濃度 の傾向 (rising / stable / falling)
    - env_status:
        - status: 室内環境ステータス (good / warning / alert)
        - label: 表示用ラベル (良好 / 注意 / 要対応)
    """
    return get_environment_summary(
        device_id=DEVICE_ID,
        lookback_minutes=LOOKBACK_MINUTES,
    )

# Google Calendar から今後の予定を取得するツール
@tool
def get_calendar_context_tool() -> Dict[str, Any]:
    """
    Google Calendar から今後の予定を取得するツールです。
    会議前の行動提案や、スケジュールに応じたアドバイスをする際に使用してください。

    以下の情報を返します:
    - has_event_within_1h: 直近1時間以内に予定があるか
    - upcoming_events: 今後の予定（開始時刻が近い順で最大3件）
    """
    return get_calendar_context()

@tool
def get_weather_context_tool(target_datetime: str) -> Dict[str, Any]:
    """
    指定日時の天気情報と季節に関する健康アラート情報を取得するツールです。
    夕方、夜、明日の朝など、特定の時間帯の天気や過ごし方についてアドバイスする際に使用してください。

    引数:
    - target_datetime: ISO 8601 形式の日時文字列
      例: 2026-04-20T18:00:00+09:00

    以下の情報を返します:
    - weather:
        - condition: 指定日時に近い時間の天気
        - temperature_c: 指定日時に近い時間の外気温
        - humidity: 指定日時に近い時間の外気湿度
        - temp_max_c: その日の最高気温
        - temp_min_c: その日の最低気温
    - season_context:
        - season: summer / winter / other
        - month: 対象日時の月
    - health_alerts:
        - heat_risk: 熱中症対策が必要か
        - dryness_risk: 乾燥対策が必要か
    """
    return get_weather_context()

# LINE に返信するツール (replyToken)
@tool
def reply_line_message_tool(reply_token: str, message: str) -> str:
    """
    LINE ユーザにメッセージを返信するツールです。
    最終的な回答をする際は、このツールを使用してください。

    引数:
    - reply_token: LINE の replyToken
    - message: 返信するメッセージ本文
    """
    print("reply_message:", message)
    reply_line_message(reply_token, message)
    return "LINE にメッセージを返信しました。"
