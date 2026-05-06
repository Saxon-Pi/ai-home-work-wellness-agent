"""
Lambda 上で擬似 MCP Server として動作するエントリポイント
tool_name と arguments を受け取り、tool_registry に定義されたツール関数を実行する
"""

import json
from typing import Any, Dict
from tool_registry import TOOLS

# handler を Gateway 入力にも対応させる
def parse_request(event, context):
    # Lambda Invoke wrapper 経由 (既存)
    if "body" in event:
        body = json.loads(event.get("body") or "{}")
        return body.get("tool_name"), body.get("arguments", {})

    # AgentCore Gateway 経由
    tool_name = None
    try:
        original_tool_name = context.client_context.custom.get(
            "bedrockAgentCoreToolName"
        )
        if original_tool_name and "___" in original_tool_name:
            tool_name = original_tool_name.split("___", 1)[1]
        else:
            tool_name = original_tool_name
    except Exception:
        pass

    return tool_name, event

# レスポンス構造の統一
def response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }

def handler(event, context):
    try:
        print(f"[AgentCore Gateway Event] {json.dumps(event, ensure_ascii=False)}", flush=True)
        
        tool_name, arguments = parse_request(event, context)

        # 辞書からツールの関数を検索
        tool_def = TOOLS.get(tool_name)
        # 存在しない tool_name が来たらエラー
        if not tool_def:
            return response(400, {
                "ok": False,
                "error": f"Unknown tool: {tool_name}",
            })
        
        # ツール実行結果
        result = tool_def["handler"](arguments)

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
