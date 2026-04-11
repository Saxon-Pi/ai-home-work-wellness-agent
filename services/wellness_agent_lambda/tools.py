"""
Strands Agent がデータ取得やLINE通知をするために使用するツール群
"""

from typing import Any, Dict
from strands import tool

# 既存の Lambda 関数から関数をインポート
from handler import (
    DEVICE_ID,
    LOOKBACK_MINUTES,       # データ取得期間 (min)
    get_recent_sensor_data, # 特定のデバイスID から送られてきた室内環境データを取得する関数
    summarize_sensor_data,  # センサデータの整理、CO2トレンドの分類 (下降/安定/上昇) をする関数
    classify_environment,   # 室内環境ステータスの分類 (良好/注意/要対応) をする関数
    format_line_message,    # Agent の回答を基に LINE メッセージを作成する関数
    send_line_message as send_line_message_impl, # LINE メッセージを送信する関数
)

# 直近1時間の室内環境データを取得し、要約した結果を返す
# 出力は最新値、1時間平均、1時間最大、CO2トレンド、環境ステータスを含む
@tool
def get_environment_summary() -> Dict[str, Any]:
    items = get_recent_sensor_data(
        device_id=DEVICE_ID,
        lookback_minutes=LOOKBACK_MINUTES,
    )

    if not items:
        return {
            "ok": False,
            "message": "センサーデータが取得できませんでした。"
        }

    summary = summarize_sensor_data(items)
    env_status = classify_environment(summary)

    return {
        "ok": True,
        "summary": summary,
        "env_status": env_status,
    }
