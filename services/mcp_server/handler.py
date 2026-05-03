"""
Lambda 上で擬似 MCP Server として動作するエントリポイント
tool_name と arguments を受け取り、tool_registry に定義されたツール関数を実行する
"""

import json
from typing import Any, Dict
from tool_registry import TOOLS

# レスポンス構造の統一
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
