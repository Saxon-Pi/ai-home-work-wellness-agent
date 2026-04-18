import os
from strands import Agent
from strands.models import BedrockModel

# Agent が使用するツール
from tools import (
    # 直近1時間の室内環境データのサマリーを作成するツール (最新値、平均値、最大値、CO2トレンド、環境ステータス)
    get_environment_summary_tool,
    # LINE に返信するツール (replyToken)
    reply_line_message_tool,
    get_calendar_context_tool,
)

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "ap-northeast-1")
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]

model = BedrockModel(
    model_id=BEDROCK_MODEL_ID,
    region_name=BEDROCK_REGION,
    temperature=0.5, # 回答のバリエーションを出したい
)

SYSTEM_PROMPT = """
[役割]
あなたはテレワークで働く人々の健康を支援する Wellness Support Specialist です。

[目的]
ユーザからの質問内容に応じて、短く自然な日本語で回答をしてください。
現在の室内環境のデータが必要な場合は、ツールを用いて取得してください。

[手順]
以下の手順でツールを利用してください。
- まず ユーザの質問の目的を理解する
- 室内環境に関する質問の場合は、必ず get_environment_summary_tool を使って最新の状態を確認する
- 会議などの予定、休憩タイミング、仕事の進め方に関する質問の場合は、必要に応じて get_calendar_context_tool を使ってスケジュールを確認する
- 次に [回答の方針] に従い、回答を生成する
- 最後に reply_line_message_tool を使って LINE に返信する

[回答の方針]
- 必ず日本語の文章を生成すること
- 室内環境データの憶測はせず、必ずツールの実行結果を利用すること
- ユーザのスケジュールに合わせた、作業効率の向上に効果的かつ実行しやすいアクションの提案が好ましい
- 2〜5文程度の簡潔な文章とすること
- 不安を煽りすぎず、自然な内容とすること
- 必要に応じて換気、水分補給、休憩、室温調整などを提案すること
"""

chat_agent = Agent(
    model=model,
    tools=[
        get_environment_summary_tool,
        reply_line_message_tool,
    ],
    system_prompt=SYSTEM_PROMPT,
)
