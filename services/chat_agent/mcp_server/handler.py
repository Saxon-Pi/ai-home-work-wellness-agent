# まずは簡易Lambda分離
# → @mcp.tool は使わず、handler.py で tool_name を受け取って core.py を呼ぶ

# TODO: 
# @mcp.tool を使って、Streamable HTTP / SSE などで MCP Server を公開し、
# chat_agent から HTTP MCPClient で接続する

import json
from typing import Any, Dict

from common.core import (
    get_weather_context,
    get_calendar_context,
    generate_sensor_chart_report,
)

def response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }

def handler(event, context):
    try:
        body = json.loads(event.get("body") or "{}")

        tool_name = body.get("tool_name")
        arguments = body.get("arguments", {})

        if tool_name == "get_weather_context_tool":
            result = get_weather_context(
                target_datetime=arguments.get("target_datetime")
            )

        elif tool_name == "get_calendar_context_tool":
            result = get_calendar_context()

        elif tool_name == "generate_sensor_chart_report_tool":
            result = generate_sensor_chart_report(
                period=arguments.get("period", "1d")
            )

        else:
            return response(400, {
                "ok": False,
                "error": f"Unknown tool: {tool_name}",
            })

        return response(200, {
            "ok": True,
            "result": result,
        })

    except Exception as e:
        print(f"[MCP Lambda] error: {e}", flush=True)
        return response(500, {
            "ok": False,
            "error": str(e),
        })
