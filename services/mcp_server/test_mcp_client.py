"""
ローカル環境で MCP Server の天気予報ツールをテストするスクリプト

1. ローカル環境で MCP Server の起動

export WEATHER_LATITUDE="35.681236"
export WEATHER_LONGITUDE="139.767125"
PYTHONPATH="$PWD/layer/python:$PWD" python -m services.mcp_server.server

2. 別ターミナルで当スクリプトを実行

source .venv/bin/activate
PYTHONPATH="$PWD/layer/python:$PWD" python -m services.mcp_server.test_mcp_client

3. 実行結果の確認
以下のような出力が返ってくれば MCP Server 上でツール実行が成功している
ツール一覧取得 → get_weather_context_tool を MCP 経由で実行 → 結果を MCP response として取得できていることを確認

tools: ['get_weather_context_tool', 'get_calendar_context_tool', 'generate_sensor_chart_report_tool']
"meta=None content="[
   TextContent("type=""text",
   "text=""{\n  \"ok\": true,\n  \"weather\": {\n    \"condition\": \"一部曇り\",\n    \"temperature_c\": 14.7,\n    \"humidity\": 77,\n    \"temp_max_c\": 27.8,\n    \"temp_min_c\": 14.5,\n    \"target_datetime\": \"2026-05-01T10:00:00+09:00\"\n  },\n  \"season_context\": {\n    \"season\": \"other\",\n    \"month\": 5\n  },\n  \"health_alerts\": {\n    \"heat_risk\": false,\n    \"dryness_risk\": false\n  }\n}",
   "annotations=None",
   "meta=None)"
]"structuredContent="{
   "result":{
      "ok":true,
      "weather":{
         "condition":"一部曇り",
         "temperature_c":14.7,
         "humidity":77,
         "temp_max_c":27.8,
         "temp_min_c":14.5,
         "target_datetime":"2026-05-01T10:00:00+09:00"
      },
      "season_context":{
         "season":"other",
         "month":5
      },
      "health_alerts":{
         "heat_risk":false,
         "dryness_risk":false
      }
   }
}"isError=False"

4. MCP Server の確認
MCP 側のログも正常にリクエストを受け付けていることを確認

INFO:     Started server process [16389]
INFO:     Waiting for application startup.
StreamableHTTP session manager started
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
Created new transport with session ID: 57faa5fd2dbe463a98675c6c7c28dd6a
INFO:     127.0.0.1:63346 - "POST /mcp HTTP/1.1" 200 OK
INFO:     127.0.0.1:63347 - "POST /mcp HTTP/1.1" 202 Accepted
INFO:     127.0.0.1:63348 - "GET /mcp HTTP/1.1" 200 OK
INFO:     127.0.0.1:63349 - "POST /mcp HTTP/1.1" 200 OK
Processing request of type ListToolsRequest
INFO:     127.0.0.1:63350 - "POST /mcp HTTP/1.1" 200 OK
Processing request of type CallToolRequest
[Weather] target: 2026-05-01T10:00:00+09:00
[Weather] result: 一部曇り, 14.7C, 77%
Terminating session: 57faa5fd2dbe463a98675c6c7c28dd6a
INFO:     127.0.0.1:63353 - "DELETE /mcp HTTP/1.1" 200 OK
"""

import asyncio
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

async def main():
    async with streamablehttp_client("http://127.0.0.1:8000/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("tools:", [tool.name for tool in tools.tools])

            result = await session.call_tool(
                "get_weather_context_tool",
                {
                    "target_datetime": "2026-05-01T10:00:00+09:00"
                },
            )
            print(result)

asyncio.run(main())
