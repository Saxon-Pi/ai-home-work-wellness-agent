"""
Strands Agent がデータ取得や LINE 通知をするために使用するツール群
"""

from typing import Any, Dict
from strands import tool

# 既存の Lambda 関数から関数をインポート
from core import (
    DEVICE_ID,        # デバイスID
    LOOKBACK_MINUTES, # データ取得期間 (デフォルトは1時間)
    # 直近1時間の室内環境サマリを取得する関数 (最新値、平均値、最大値、CO2トレンド、環境ステータス)
    get_environment_summary,
    # Agent の回答を基に LINE メッセージを作成する関数
    format_line_message,
    # LINE メッセージを送信する関数
    send_line_message,
)

# 直近1時間の室内環境データを取得し、要約した結果を返すツール
# 出力は最新値、平均値、最大値、CO2トレンド(下降/安定/上昇)、環境ステータス(良好/注意/用対応)を含む
@tool
def get_environment_summary_tool() -> Dict[str, Any]:
    return get_environment_summary(
        device_id=DEVICE_ID,
        lookback_minutes=LOOKBACK_MINUTES,
    )

# 室内環境サマリと Agent が生成したアドバイスを組み合わせて、LINE メッセージを作成するツール
@tool
def format_line_message_tool(advice: str) -> Dict[str, Any]:
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
    send_line_message(message)
    return "LINEにメッセージを送信しました。"
