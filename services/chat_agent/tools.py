"""
Chat Agent が室内環境、カレンダー、天気情報の取得、レポート作成と LINE 返信を行うために使用するツール群
これらのツールは、LINE Webhook から起動される Chat Agent から利用されることを想定している

[Agent の動作フロー]
- 現在の室内環境を確認
- 今後の予定を確認
- 現在の天気や気象リスクを確認
- 上記に関する質問の回答を生成
- 室内環境レポートの作成を要求された場合は、グラフとコメントを生成
- 最終的な返答を LINE に送信

[アーキテクチャ]
一部ツールは Chat Agent Lambda ではなく、MCP Server Lambda (mcpServerFn) 上で実行される

Lambda 分離の目的は以下
- ツール実行ロジックの分離
- 権限の最小化（Chat Agent 側に不要なAWS権限を持たせない）
- 将来的な MCP Server（HTTP化）への移行を容易にする

[対象ツール]
以下のツールは MCP Server Lambda 経由で実行される
- get_weather_context_tool
- get_calendar_context_tool
- generate_sensor_chart_report_tool

[実行フロー]
chat_agent (Lambda)
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

import urllib.request
import sys
import os
import json
from typing import Any, Dict
import boto3
from strands import tool
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

# 既存の Lambda 関数から関数をインポート
# Lambda Layer から core.py を読み込む
from common.core import (
    DEVICE_ID,        # デバイスID
    LOOKBACK_MINUTES, # データ取得期間 (デフォルトは1時間)
    # 直近1時間の室内環境サマリを取得する関数 (最新値、平均値、最大値、CO2トレンド、環境ステータス)
    get_environment_summary,
    # LINE のチャットに応答する関数
    reply_line_message,
    # テキストと画像を送信する関数
    reply_line_text_and_image_message,
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

# AgentCore Gateway の URL にリクエストを投げて MCP ツールを実行する
def invoke_gateway_tool(tool_name: str, arguments: dict):
    url = os.environ["AGENTCORE_GATEWAY_URL"]
    
    payload = {
        "tool_name": tool_name,
        "arguments": arguments
    }

    session = boto3.Session()
    credentials = session.get_credentials()

    request = AWSRequest(
        method="POST",
        url=url,
        data=json.dumps(payload),
        headers={"Content-Type": "application/json"},
    )

    SigV4Auth(credentials, "execute-api", session.region_name).add_auth(request)

    response = urllib.request.post(
        url,
        headers=dict(request.headers),
        data=request.body
    )

    return response.json()

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

# @tool
# def get_weather_context_tool(target_datetime: str) -> dict:
    # """
    # 指定日時の天気情報と季節に関する健康アラート情報を取得するツールです。
    # 夕方、夜、明日の朝など、特定の時間帯の天気や過ごし方についてアドバイスする際に使用してください。

    # 引数:
    # - target_datetime: ISO 8601 形式の日時文字列
    #   例: 2026-04-20T18:00:00+09:00

    # 以下の情報を返します:
    # - weather:
    #     - condition: 指定日時に近い時間の天気
    #     - temperature_c: 指定日時に近い時間の外気温
    #     - humidity: 指定日時に近い時間の外気湿度
    #     - temp_max_c: その日の最高気温
    #     - temp_min_c: その日の最低気温
    # - season_context:
    #     - season: summer / winter / other
    #     - month: 対象日時の月
    # - health_alerts:
    #     - heat_risk: 熱中症対策が必要か
    #     - dryness_risk: 乾燥対策が必要か
    # """
#     return invoke_mcp_tool(
#         "get_weather_context_tool",
#         {"target_datetime": target_datetime},
#     )

# @tool
# def get_weather_context_tool(target_datetime: str):
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
#     return invoke_gateway_tool(
#         "get_weather_context_tool",
#         {"target_datetime": target_datetime},
#     )

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

@tool
def generate_sensor_chart_report_tool(period: str) -> dict:
    """
    指定期間の室内環境データからグラフレポートを生成するツールです。
    ユーザが室内環境の推移やグラフ表示を求めた場合に使用してください。

    引数:
    - period: 取得期間 (使用できる値は "1h", "1d", "7d")

    以下の情報を返します:
    - image_url: 生成したグラフ画像の URL
    - summary: グラフ生成結果のサマリ
    - chart_data.summary_stats: CO2/温度/湿度 の 最小/最大/平均/傾向
    """
    return invoke_mcp_tool(
        "generate_sensor_chart_report_tool",
        {"period": period},
    )

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
    print(f"reply_message: {message}", file=sys.stderr, flush=True)
    reply_line_message(reply_token, message)
    return "LINE にメッセージを返信しました。"

@tool
def reply_line_text_and_image_message_tool(reply_token: str, message: str, image_url: str,) -> str:
    """
    テキストと画像を LINE ユーザに同時返信するツールです。
    室内環境データのグラフ画像と、そのグラフに基づく簡単なレポートや推奨アクションを
    ユーザーへ送信する際に使用してください。

    引数:
    - reply_token: LINE Webhook イベントに含まれる replyToken
    - message: 室内環境データの傾向や推奨アクションを含むレポート本文
    - image_url: 返信するグラフ画像のURL
    """
    print(f"reply_message: {message}", file=sys.stderr, flush=True)
    safe_image_url = image_url.split("?")[0]
    print(f"reply_image_url: {safe_image_url}", file=sys.stderr, flush=True)
    reply_line_text_and_image_message(reply_token, message, image_url)
    return "LINEにテキストと画像を返信しました。"


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

# @tool
# def generate_sensor_chart_report_tool(period: str) -> Dict[str, Any]:
#     """
#     指定期間の室内環境データからグラフレポートを生成するツールです。
#     ユーザが室内環境の推移やグラフ表示を求めた場合に使用してください。

#     引数:
#     - period: 取得期間 (使用できる値は "1h", "1d", "7d")

#     以下の情報を返します:
#     - image_url: 生成したグラフ画像の URL
#     - chart_data.summary_stats: CO2/温度/湿度 の 最小/最大/平均/傾向
#     - summary: グラフ生成結果のサマリ
#     """
#     return generate_sensor_chart_report(period=period)

""" 未使用ツール """
# @tool
# def reply_line_image_message_tool(reply_token: str, image_url: str) -> str:
#     """
#     画像を LINE ユーザに返信するツールです。
#     グラフ画像をユーザへ送信する際は、このツールを使用してください。

#     引数:
#     - reply_token: LINE Webhook イベントに含まれる replyToken
#     - image_url: 返信する画像のURL
#     """
#     reply_line_image_message(reply_token=reply_token, image_url=image_url)
#     return "LINEに画像を返信しました。"
