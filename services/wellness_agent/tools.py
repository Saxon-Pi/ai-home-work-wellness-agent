"""
室内環境データの取得、LINE メッセージ生成、LINE へのメッセージ送信 を行うために使用するツール群
これらのツールは、定期実行される Wellness Agent から利用されることを想定している

Agent はこれらのツールを使い、以下の流れで動作する
- 現在の室内環境を確認
- 室内環境に応じたアドバイスを生成
- LINE に送信するメッセージ本文を構築
- 最終的な通知を LINE に送信
"""

from typing import Any, Dict
from strands import tool

# 既存の Lambda 関数から関数をインポート
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

# 室内環境サマリと Agent が生成したアドバイスを組み合わせて、LINE メッセージを作成するツール
@tool
def format_line_message_tool(advice: str) -> Dict[str, Any]:
    """
    室内環境サマリと Agent が生成したアドバイス文を組み合わせて、
    LINE 送信用のメッセージ本文を生成するツールです。
    ユーザ向けの最終通知メッセージを作成する際に使用してください。

    引数:
    - advice: Agent が生成した日本語のアドバイス文

    返り値:
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
    print("send_message:", message)
    send_line_message(message)
    return "LINE にメッセージを送信しました。"
