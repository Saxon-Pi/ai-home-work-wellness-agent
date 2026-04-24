"""
LINEメッセージをトリガーに起動し、Strands Agent で応答を生成・返信する Lambda 関数

LINEユーザー
→ LINE Platform
→ Webhook URL
→ API Gateway
→ Lambda (handler.py)
"""

import json
from datetime import datetime, timedelta, timezone

# services.wellness_agent.agent から chat_agent を読み込む
from agent import chat_agent

JST = timezone(timedelta(hours=9))
now_jst = datetime.now(JST).isoformat()

def handler(event, context):
    print("event:", json.dumps(event, ensure_ascii=False))

    body = json.loads(event.get("body", "{}"))
    events = body.get("events", [])

    if not events:
        return {
            "statusCode": 200,
            "body": "ok",
        }

    line_event = events[0]
    event_type = line_event.get("type")

    if event_type != "message":
        return {
            "statusCode": 200,
            "body": "ok",
        }

    message = line_event.get("message", {})
    if message.get("type") != "text":
        return {
            "statusCode": 200,
            "body": "ok",
        }

    # Webhook イベントに対して返信するための一時トークン
    reply_token = line_event["replyToken"]
    # ユーザメッセージ
    user_text = message["text"]

    user_request = f"""
現在の日時は {now_jst} です（JST）。

ユーザから LINE で以下のメッセージを受け取りました。
内容を理解し、必要に応じてツールを使用し、LINE に返信してください。

ユーザーが「今」、「今夜」、「明日の朝」などの時間表現を使った場合は、
必ず現在日時を基準に target_datetime を解釈してください。

replyToken: {reply_token}
ユーザメッセージ: {user_text}
""".strip()

    # Agent 実行
    agent_response = chat_agent(user_request)

    print("agent_response:", str(agent_response))

    return {
        "statusCode": 200,
        "body": "ok",
    }
