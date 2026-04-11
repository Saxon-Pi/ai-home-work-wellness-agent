"""
Strands Agent がデータ取得や LINE 通知をするために使用するツール群
"""

from typing import Any, Dict
from strands import tool

# 既存の Lambda 関数から関数をインポート
from services.wellness_agent_lambda.core import (
    DEVICE_ID,
    LOOKBACK_MINUTES,       # データ取得期間 (デフォルトは1時間に設定)
    get_recent_sensor_data, # 特定のデバイスID から送られてきた、直近1時間の室内環境データを取得する関数
    summarize_sensor_data,  # センサデータの整理、CO2トレンドの分類 (下降/安定/上昇) をする関数
    classify_environment,   # 室内環境ステータスの分類 (良好/注意/要対応) をする関数
    format_line_message,    # Agent の回答を基に LINE メッセージを作成する関数
    send_line_message as send_line_message_impl, # LINE メッセージを送信する関数
)

# 直近1時間の室内環境データを取得し、要約した結果を返すツール
# 出力は最新値、1時間平均、1時間最大、CO2トレンド、環境ステータスを含む
@tool
def get_environment_summary() -> Dict[str, Any]:
    items = get_recent_sensor_data(
        device_id=DEVICE_ID,
        lookback_minutes=LOOKBACK_MINUTES,
    )

    if not items:
        error_message = "センサーデータが取得できませんでした。デバイスの状態を確認してください。"
        print("error:", error_message)

        return {
            "ok": False,
            "message": error_message,
        }

    summary = summarize_sensor_data(items)
    env_status = classify_environment(summary)

    return {
        "ok": True,
        "summary": summary,
        "env_status": env_status,
    }

# 指定されたメッセージを LINE に送信するツール
@tool
def send_line_message_tool(message: str) -> str:
    send_line_message_impl(message)
    return "LINEにメッセージを送信しました。"

# 室内環境データと Agent が生成したアドバイスを組み合わせて、LINE メッセージを作成するツール
@tool
def format_line_message_tool(advice: str) -> Dict[str, Any]:
    items = get_recent_sensor_data(
        device_id=DEVICE_ID,
        lookback_minutes=LOOKBACK_MINUTES,
    )

    if not items:
        error_message = "センサーデータが取得できませんでした。デバイスの状態を確認してください。"
        print("error:", error_message)

        return {
            "ok": False,
            "message": error_message,
        }

    summary = summarize_sensor_data(items)
    env_status = classify_environment(summary)
    line_message = format_line_message(
        summary=summary,
        status_label=env_status["label"],
        advice=advice,
    )

    return {
        "ok": True,
        "line_message": line_message,
        "env_status": env_status,
        "summary": summary,
    }
