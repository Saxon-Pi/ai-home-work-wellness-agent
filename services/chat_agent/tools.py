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
)

# 直近1時間の室内環境データを取得し、要約した結果を返すツール
# 出力は最新値、平均値、最大値、CO2トレンド(下降/安定/上昇)、環境ステータス(良好/注意/用対応)を含む
@tool
def get_environment_summary_tool() -> Dict[str, Any]:
    return get_environment_summary(
        device_id=DEVICE_ID,
        lookback_minutes=LOOKBACK_MINUTES,
    )

# LINE に返信するツール (replyToken)
@tool
def reply_line_message_tool(reply_token: str, message: str) -> str:
    reply_line_message(reply_token, message)
    print("reply_message:", message)
    return "LINEに返信しました。"
