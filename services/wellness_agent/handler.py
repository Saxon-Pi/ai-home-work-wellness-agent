"""
EventBridge から定期実行される Strands Agent のオーケストレーターとしての Lambda 関数
- 室内環境サマリを取得
- 通知可否を判定
- 通知が必要な場合は Agent を実行
- 実行後に室内環境ステータスを保存

LINE 通知条件: 
EventBridge により 9:00 ~ 23:00 の間に 10分間隔で Agent Lambdaが実行される
そのうち、以下の通知ルールに当てはまれば LINEメッセージを送信する
- 前回の通知情報が存在しない場合
- 室内環境ステータスが変化した場合（例：注意 → 要対応、要対応 → 良好、など）
- 室内環境ステータスが「要対応」のまま 30分経過した場合
- ステータスが「良好」、「注意」のまま 1時間経過した場合
"""

import time
from agent import agent
from services.common.core import (
    DEVICE_ID,        # デバイスID
    LOOKBACK_MINUTES, # データ取得期間 (デフォルトは1時間)
    # 直近1時間の室内環境サマリを取得する関数 (最新値、平均値、最大値、CO2トレンド、環境ステータス)
    get_environment_summary,
    # 前回の通知情報（室内環境ステータスなど）を保存する関数
    save_agent_state,
    # 前回の通知情報を取得する関数
    get_last_agent_state,
    # LINE 通知の要否を判定する関数 (平常時に短期間の通知を抑える目的)
    should_send_notification,
)

def handler(event, context):
    result = get_environment_summary(
        device_id=DEVICE_ID,
        lookback_minutes=LOOKBACK_MINUTES,
    )

    if not result["ok"]:
        error_message = result["message"]
        print("error:", error_message)
        return {
            "ok": False,
            "message": error_message,
        }
    
    summary = result["summary"]
    env_status = result["env_status"]

    # 前回の室内環境ステータスと時刻から通知可否を判定
    now_ms = int(time.time() * 1000)
    last_state = get_last_agent_state(DEVICE_ID)

    # TRUE(通知OK) / FALSE(通知NG)
    should_send = should_send_notification(
        current_status=env_status["status"],
        last_state=last_state,
        now_ms=now_ms,
    )

    # 通知NG なら通知せずに終了
    if not should_send:
        print("notification_sent:", False)
        print("summary:", summary)
        print("env_status:", env_status)
        return {
            "ok": True,
            "summary": summary,
            "env_status": env_status,
            "notification_sent": False,
        }
    
    # 定期実行のためリクエストは固定
    user_request = (
        "現在の室内環境を確認し、必要に応じて健康アドバイスを作成して、"
        "LINEに送信してください。"
    )

    # Agent 実行
    agent_response = agent(user_request)

    # 通知内容と室内環境ステータスを保存
    save_agent_state(
        device_id=DEVICE_ID,         # デバイスID
        status=env_status["status"], # 室内環境ステータス
        message=str(agent_response), # LINEメッセージ
        notified_at_ms=now_ms,       # 通知時刻
    )

    print("notification_sent:", True)
    print("summary:", summary)
    print("env_status:", env_status)
    print("agent_response:", str(agent_response))

    return {
        "ok": True,
        "summary": summary,
        "env_status": env_status,
        "notification_sent": True,
        "agent_response": str(agent_response),
    }
