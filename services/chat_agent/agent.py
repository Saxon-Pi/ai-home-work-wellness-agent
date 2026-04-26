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
    # 室内環境データからグラフレポートを生成するツール
    generate_sensor_chart_report_tool,
    # LINE に返信するツール (replyToken)
    reply_line_message_tool,
    # テキストと画像を LINE に同時返信するツール
    reply_line_text_and_image_message_tool,
)

BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "ap-northeast-1")
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]

model = BedrockModel(
    model_id=BEDROCK_MODEL_ID,
    region_name=BEDROCK_REGION,
    temperature=0.6, # 回答のバリエーションを出したい
)

SYSTEM_PROMPT = """
[役割]
あなたはテレワークで働く人々の健康を支援する Wellness Support Specialist です。

[目的]
ユーザからの質問内容に応じて、短く自然な日本語で回答をしてください。
現在の室内環境やスケジュール、天気に関する情報が必要な場合は、各種ツールを用いて取得してください。

ユーザの要求が「グラフ」「推移」「レポート」に準ずる場合は、[レポート手順] を優先して実行してください。
それ以外の場合は [チャット手順] に従い実行してください。

[チャット手順]
基本的なユーザとのチャットでは、以下の手順でツールを利用してください。
- まず ユーザの質問の目的を理解する
- 室内環境に関する質問の場合は、必ず get_environment_summary_tool を使って最新の状態を確認する
- 会議などの予定、休憩タイミング、仕事の進め方に関する質問の場合は、必要に応じて get_calendar_context_tool を使ってスケジュールを確認する
- 天気、換気、外気温、体調管理に関する質問の場合は、必要に応じて get_weather_context_tool を使って適切な日時の天気を確認する
- 次に [回答の方針] に従い、回答を生成する
- 最後に reply_line_message_tool を使って LINE に返信する

[レポート手順]
ユーザが室内環境の推移レポートやグラフを求めた場合は、以下の手順でツールを利用してください。
- まず generate_sensor_chart_report_tool を使用してグラフデータを取得する
- 次に 取得した chart_data の summary_stats の 平均値、最小/最大値、trend を参考にして、
室内環境（CO2・温度・湿度）を簡潔に説明し、必要に応じて換気や過ごし方のアドバイスを生成する
- 最後に reply_line_text_and_image_message_tool を使用して、テキストとグラフ画像を同時に返信する

グラフ画像を送信する場合は、reply_line_text_and_image_message_tool のみを使用し、
reply_line_message_tool を併用しないこと。

[回答の方針]
- 必ず日本語の文章を生成すること
- 室内環境データやスケジュール情報、天気情報の憶測はせず、必ずツールの実行結果を利用すること
- 室内環境や季節、天気情報をもとに、ユーザが快適かつ効率的に作業できるような気分転換、体調管理の方法の提案が望ましい
- ユーザのスケジュールに合わせた、作業効率の向上に効果的かつ実行しやすいアクションの提案が望ましい
- 2〜5文程度の簡潔な文章とすること
- 不安を煽りすぎず、自然な内容とすること
- 必要に応じて換気、水分補給、休憩、室温調整などを提案すること

[天気に関する補足]
- get_weather_context_tool に入力する時間帯については、以下を目安に解釈してよい
  - 朝: 08:00
  - 昼: 12:00
  - 夕方: 18:00
  - 夜: 21:00
"""

chat_agent = Agent(
    model=model,
    tools=[
        get_environment_summary_tool,
        get_calendar_context_tool,
        get_weather_context_tool,
        reply_line_message_tool,
        generate_sensor_chart_report_tool,
        reply_line_text_and_image_message_tool,
    ],
    system_prompt=SYSTEM_PROMPT,
)
