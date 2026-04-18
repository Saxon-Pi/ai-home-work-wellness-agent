"""
Strands Agent がデータ取得や LINE 通知をするために使用するツール群
"""

from typing import Any, Dict
from strands import tool

# 既存の Lambda 関数から関数をインポート
from common.core import ( # Lambda Layer 前提のパス
    DEVICE_ID,        # デバイスID
    LOOKBACK_MINUTES, # データ取得期間 (デフォルトは1時間)
    # 直近1時間の室内環境サマリを取得する関数 (最新値、平均値、最大値、CO2トレンド、環境ステータス)
    get_environment_summary,
    # LINE のチャットに応答する関数
    reply_line_message,
    # Google Calendar 連携用関数
    get_calendar_context,
)

# 直近1時間の室内環境データを取得し、要約した結果を返すツール
@tool
def get_environment_summary_tool() -> Dict[str, Any]:
    """
    直近1時間の室内環境データを取得するツールです。
    室内環境に関する質問の回答やアドバイス生成に使用してください。
    
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
    会議前の行動提案や、スケジュールに応じたアドバイスを行う際に使用してください。

    出力は以下となります:
    - has_event_within_1h: 直近1時間以内に予定があるか
    - upcoming_events: 今後の予定（開始時刻が近い順で最大3件）
    """
    return get_calendar_context()

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
    reply_line_message(reply_token, message)
    return "LINE にメッセージを返信しました。"
