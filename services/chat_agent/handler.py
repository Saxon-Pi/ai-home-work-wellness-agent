"""
LINEメッセージをトリガーに起動し、Strands Agent で応答を生成・返信する Lambda 関数

LINEユーザー
→ LINE Platform
→ Webhook URL
→ API Gateway
→ Lambda (handler.py)
"""

import json
from agent import chat_agent # services.chat_agent.agent の chat_agent

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
ユーザから LINE で以下のメッセージを受け取りました。
内容を理解し、必要に応じてツールを使用し、LINE に返信してください。

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
