"""
Strands Agent の定義

Agent は get_environment_summary_tool() を呼び出し、回答に必要な情報を主体的に取得する
その後、取得結果を踏まえて以下を実行する
- アドバイス生成
- LINE メッセージの整形 (tool使用)
- メッセージの送信 (tool使用)
"""

import os
from strands import Agent
from strands.models import BedrockModel

# Agent が使用するツール
from tools import (
    # 直近1時間の室内環境データのサマリーを作成するツール (最新値、平均値、最大値、CO2トレンド、環境ステータス)
    get_environment_summary_tool,
    # 室内環境サマリと Agent が生成したアドバイスを組み合わせて、LINE メッセージを作成するツール
    format_line_message_tool,
    # 指定されたメッセージを LINE に送信するツール
    send_line_message_tool,
)

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "ap-northeast-1")
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]

model = BedrockModel(
    model_id=BEDROCK_MODEL_ID,
    region_name=BEDROCK_REGION,
    temperature=0.3,
)

SYSTEM_PROMPT = """
[役割]
あなたはテレワークで働く人々の健康を支援する Wellness Support Specialist です。

[目的]
以下の室内環境データをもとに、ユーザが快適・効率的に仕事ができるように、
短く自然な日本語でアドバイスをしてください。

[手順]
以下の手順でツールを利用してください。
- まず get_environment_summary_tool を使って、現在の室内環境を確認する
- 次に 室内環境サマリをもとに [アドバイスのルール] に従い、回答を生成する
- その後 format_line_message_tool を使って LINE メッセージを作成する
- 最後に send_line_message_tool を使ってメッセージを送信する

[アドバイスのルール]
- 必ず日本語の文章を生成すること
- 憶測はせず、必ずツールの実行結果に基づいたアドバイスを生成すること
- 2〜4文程度の簡潔な文章とすること
- 不安を煽りすぎず、自然な内容とすること
- 必要に応じて換気、水分補給、休憩、室温調整などを提案すること
- 数値の異常（CO2や温度など）がある場合は優先的に言及すること
"""

agent = Agent(
    model=model,
    tools=[
        get_environment_summary_tool,
        format_line_message_tool,
        send_line_message_tool,
    ],
    system_prompt=SYSTEM_PROMPT,
)
