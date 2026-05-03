"""
【テスト用スクリプト】
ローカル環境で起動した MCP Server の天気予報ツールを、
ローカル環境の Agent からツール実行するスクリプト

ローカルAgent
  ↓
HTTP MCP Client
  ↓
ローカルMCP Server
  ↓
@mcp.tool get_weather_context_tool
  ↓
core.py
  ↓
天気結果取得

1. ローカル環境で MCP Server の起動

export WEATHER_LATITUDE="35.681236"
export WEATHER_LONGITUDE="139.767125"
PYTHONPATH="$PWD/layer/python:$PWD" python -m services.mcp_server.server

2. 別ターミナルで Agent にツールを実行させる

export AWS_PROFILE=<your-profile>
export AWS_REGION=<your-region>
export BEDROCK_MODEL_ID="global.anthropic.claude-sonnet-4-20250514-v1:0"
export BEDROCK_REGION="ap-northeast-1"
PYTHONPATH="$PWD/services/chat_agent:$PWD/layer/python:$PWD" \
python services/chat_agent/test_agent_mcp.py

3. 実行結果の確認
以下のような出力が返ってくれば MCP Server 上で Agent によるツール実行が成功している
Agent がツール一覧取得 → get_weather_context_tool を MCP 経由で実行 → 結果を MCP response として取得 → Agent が回答生成

実行ログ：
2026年5月1日10時の天気情報を取得しますね。
Tool #1: get_weather_context_tool
Tool #2: reply_line_message_tool
reply_message: 2026年5月1日10時は一部曇りで、気温14.7℃、湿度77%の予報です。日中は最高27.8℃まで上がる予定なので、
朝は少し肌寒く感じるかもしれませんが、日中に向けて暖かくなりそうですね。温度調整しやすい服装がおすすめです。
"""

from agent import chat_agent

response = chat_agent("2026-05-01T10:00:00+09:00 の天気を教えて")
print(response)
