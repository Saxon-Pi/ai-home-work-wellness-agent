"""
Wellness Agent が室内環境、カレンダー、天気情報の取得と LINE 通知を行うために使用するツール群
これらのツールは、EventBridge から定期実行される Wellness Agent から利用されることを想定している

[Agent の動作フロー]
- 現在の室内環境を確認
- 今後の予定を確認
- 現在の天気や気象リスクを確認
- 上記に関する通知メッセージを生成
- 最終的な通知を LINE に送信

[アーキテクチャ]
一部ツールは Wellness Agent Lambda ではなく、MCP Server Lambda (mcpServerFn) 上で実行される

Lambda 分離の目的は以下
- ツール実行ロジックの分離
- 権限の最小化（Wellness Agent 側に不要なAWS権限を持たせない）
- 将来的な MCP Server（HTTP化）への移行を容易にする

[対象ツール]
以下のツールは MCP Server Lambda 経由で実行される
- get_weather_context_tool
- get_calendar_context_tool

[実行フロー]
wellness_agent (Lambda)
  ↓ @tool 呼び出し
get_weather_context_tool()
  ↓
invoke_mcp_tool()
  ↓ Lambda Invoke
mcpServerFn
  ↓ handler.py
tool_name に応じて処理を分岐
  ↓
core.py の各関数を実行

[備考]
- 現在は Lambda Invoke による「擬似MCP構成」となる
- server.py に FastMCP による正式 MCP 実装があり、将来的に HTTP MCP Server に移行可能
"""

import sys
import os
import json
from typing import Any, Dict
import boto3
from strands import tool

# 既存の Lambda 関数から関数をインポート
# Lambda Layer から core.py を読み込む
from common.core import ( # Lambda Layer 前提のパス
    DEVICE_ID,        # デバイスID
    LOOKBACK_MINUTES, # データ取得期間 (デフォルトは1時間)
    # 直近1時間の室内環境サマリを取得する関数 (最新値、平均値、最大値、CO2トレンド、環境ステータス)
    get_environment_summary,
    # Agent の回答を基に LINE メッセージを作成する関数
    format_line_message,
    # LINE メッセージを送信する関数
    send_line_message,
)

# Lambda client 不要時に初期化をしない
_lambda_client = None

def get_lambda_client():
    global _lambda_client
    if _lambda_client is None:
        _lambda_client = boto3.client("lambda")
    return _lambda_client

# MCP ツール実行用 Lambda invoke ラッパー
def invoke_mcp_tool(tool_name: str, arguments: dict) -> dict:
    response = get_lambda_client().invoke(
        FunctionName=os.environ["MCP_SERVER_FUNCTION_NAME"],
        InvocationType="RequestResponse",
        Payload=json.dumps({
            "body": json.dumps({
                "tool_name": tool_name,
                "arguments": arguments,
            })
        }).encode("utf-8"),
    )

    raw_payload = response["Payload"].read().decode("utf-8")

    # Lambda実行エラー（例外発生時）
    if "FunctionError" in response:
        print(f"[MCP Invoke] function error: {raw_payload}", file=sys.stderr, flush=True)
        return {
            "ok": False,
            "message": "MCP Server Lambda の実行に失敗しました。",
        }

    # 通常レスポンス
    payload = json.loads(raw_payload)
    body = json.loads(payload.get("body", "{}"))

    if not body.get("ok"):
        return {
            "ok": False,
            "message": body.get("error", "MCP Server tool failed"),
        }

    return body["result"]

# =====================================================
#  Tools
# =====================================================

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

@tool
def get_weather_context_tool(target_datetime: str) -> dict:
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
    return invoke_mcp_tool(
        "get_weather_context_tool",
        {"target_datetime": target_datetime},
    )

@tool
def get_calendar_context_tool() -> dict:
    """
    Google Calendar から今後の予定を取得するツールです。
    会議前の行動提案や、スケジュールに応じたアドバイスをする際に使用してください。

    以下の情報を返します:
    - has_event_within_1h: 直近1時間以内に予定があるか
    - upcoming_events: 今後の予定（開始時刻が近い順で最大3件）
    """
    return invoke_mcp_tool(
        "get_calendar_context_tool",
        {},
    )

# 室内環境サマリと Agent が生成したアドバイスを組み合わせて、LINE メッセージを作成するツール
@tool
def format_line_message_tool(advice: str) -> Dict[str, Any]:
    """
    室内環境サマリと Agent が生成したアドバイス文を組み合わせて、
    LINE 送信用のメッセージ本文を生成するツールです。
    ユーザ向けの最終通知メッセージを作成する際に使用してください。

    引数:
    - advice: Agent が生成した日本語のアドバイス文

    以下の情報を返します:
    - line_message: LINE に送信する完成済みメッセージ
    - summary: 室内環境サマリ
    - env_status: 室内環境ステータス
    """
    result = get_environment_summary(
        device_id=DEVICE_ID,
        lookback_minutes=LOOKBACK_MINUTES,
    )

    if not result["ok"]:
        return result

    summary = result["summary"]
    env_status = result["env_status"]

    line_message = format_line_message(
        summary=summary,
        status_label=env_status["label"],
        advice=advice,
    )

    return {
        "ok": True,
        "line_message": line_message,
        "summary": summary,
        "env_status": env_status,
    }

# 指定されたメッセージを LINE に送信するツール
@tool
def send_line_message_tool(message: str) -> str:
    """
    LINE ユーザに指定されたメッセージを送信するツールです。
    定期通知の最終ステップで使用してください。

    引数:
    - message: 信する最終メッセージ本文
    """
    print(f"send_message: {message}", file=sys.stderr, flush=True)
    send_line_message(message)
    return "LINE にメッセージを送信しました。"


""" MCP化前のツールはコメントアウトしている """
# # Google Calendar から今後の予定を取得するツール
# @tool
# def get_calendar_context_tool() -> Dict[str, Any]:
#     """
#     Google Calendar から今後の予定を取得するツールです。
#     会議前の行動提案や、スケジュールに応じたアドバイスをする際に使用してください。

#     以下の情報を返します:
#     - has_event_within_1h: 直近1時間以内に予定があるか
#     - upcoming_events: 今後の予定（開始時刻が近い順で最大3件）
#     """
#     return get_calendar_context()

# @tool
# def get_weather_context_tool(target_datetime: str) -> Dict[str, Any]:
#     """
#     指定日時の天気情報と季節に関する健康アラート情報を取得するツールです。
#     夕方、夜、明日の朝など、特定の時間帯の天気や過ごし方についてアドバイスする際に使用してください。

#     引数:
#     - target_datetime: ISO 8601 形式の日時文字列
#       例: 2026-04-20T18:00:00+09:00

#     以下の情報を返します:
#     - weather:
#         - condition: 指定日時に近い時間の天気
#         - temperature_c: 指定日時に近い時間の外気温
#         - humidity: 指定日時に近い時間の外気湿度
#         - temp_max_c: その日の最高気温
#         - temp_min_c: その日の最低気温
#     - season_context:
#         - season: summer / winter / other
#         - month: 対象日時の月
#     - health_alerts:
#         - heat_risk: 熱中症対策が必要か
#         - dryness_risk: 乾燥対策が必要か
#     """
#     return get_weather_context(target_datetime=target_datetime)
