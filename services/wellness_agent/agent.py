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
    # Google Calendar から今後の予定を取得するツール
    get_calendar_context_tool,
    # Open-Meteo から天気情報を取得するツール
    get_weather_context_tool,
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
    temperature=0.4,
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
- 会議など、予定前後の行動や休憩タイミングに関してアドバイスができる場合は、get_calendar_context_tool を使ってスケジュールを確認する
- 天気、換気、外気温、体調管理に関してアドバイスができる場合は、get_weather_context_tool を使って適切な日時の天気を確認する
- 次に 室内環境サマリをもとに [回答の方針] に従い、回答を生成する
- その後 format_line_message_tool を使って LINE メッセージを作成する
- 最後に send_line_message_tool を使ってメッセージを送信する

[回答の方針]
- 必ず日本語の文章を生成すること
- 室内環境データやスケジュール情報、天気情報の憶測はせず、必ずツールの実行結果を利用すること
- 室内環境や季節、天気情報をもとに、ユーザが快適かつ効率的に作業できるような気分転換、体調管理の方法の提案が望ましい
- ユーザのスケジュールに合わせた、作業効率の向上に効果的かつ実行しやすいアクションの提案が望ましい
- 2〜5文程度の簡潔な文章とすること
- 不安を煽りすぎず、自然な内容とすること
- 必要に応じて換気、水分補給、休憩、室温調整などを提案すること

[予定と天気を組み合わせる場合]
- ユーザがスケジュールのイベントに関連した天気を質問した場合は、先に get_calendar_context_tool を使って予定時刻を確認すること
- 予定時刻が取得できた場合は、その予定開始時刻に近い日時を target_datetime として get_weather_context_tool を使うこと
- 例: 「明日の試験に傘は必要？」→ カレンダー確認 → 明日の試験開始時刻を取得 → その時刻の天気を確認 → 傘の要否を回答

[天気に関する補足]
- 通知時点の外気状況を見る場合は、現在時刻に近い日時を get_weather_context_tool に指定する
- 朝、昼、夕方、夜などの時間帯について考慮が必要な場合は、以下を目安に解釈してよい
  - 朝: 08:00
  - 昼: 12:00
  - 夕方: 18:00
  - 夜: 21:00
"""

wellness_agent = Agent(
    model=model,
    tools=[
        # wellnessAgentFn 上で実行するツール
        get_environment_summary_tool,
        format_line_message_tool,
        send_line_message_tool,
        # mcpServerFn 上で実行するツール
        get_calendar_context_tool,
        get_weather_context_tool,
    ],
    system_prompt=SYSTEM_PROMPT,
)
