"""
NOTE:
server.py は FastMCP による正式な MCP Server 実装となる
現在の Lambda 環境では handler.py を経由した擬似 MCP 構成を利用しているが、
 (services/mcp_server/handler.py 内の tool routing で制御)
将来的に HTTP MCP Server として公開する際には、こちらを使用する

[実行フロー]
chat_agent (wellness_agent)
  ↓
mcp_tools_client
(Agent は mcp_tools_client を「ツール群」として扱う)
  ↓ HTTP
MCP Server /mcp
  ↓
@mcp.tool の get_weather_context_tool
(server.py の @mcp.tool がツール定義になる)
  ↓
core.py
"""

from mcp.server.fastmcp import FastMCP
from tool_registry import TOOLS, weather_tool, calendar_tool, report_tool

mcp = FastMCP("wellness-tools")

@mcp.tool(description=TOOLS["get_weather_context_tool"]["description"])
def get_weather_context_tool(target_datetime: str):
    return weather_tool({"target_datetime": target_datetime})

@mcp.tool(description=TOOLS["get_calendar_context_tool"]["description"])
def get_calendar_context_tool():
    return calendar_tool({})

@mcp.tool(description=TOOLS["generate_sensor_chart_report_tool"]["description"])
def generate_sensor_chart_report_tool(period: str):
    return report_tool({"period": period})

if __name__ == "__main__":
    mcp.run(transport="streamable-http")

# MCP Server を HTTP サーバーとして起動する
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
