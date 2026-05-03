"""
ツールの共通定義（名前・説明・実行関数）を管理するモジュール
handler.py（Lambda 実行）と server.py（FastMCP 公開）の両方から参照され、ツール定義の一元化を行う

mcp_server/
  ├── tool_registry.py  ← ツール定義
  ├── handler.py        ← Lambda Invoke 用
  └── server.py         ← FastMCP 用
"""

from typing import Any, Dict

from common.core import (
    get_weather_context,
    get_calendar_context,
    generate_sensor_chart_report,
)

def weather_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    指定日時の天気情報と季節に関する健康アラート情報を取得するツールです。
    夕方、夜、明日の朝など、特定の時間帯の天気や過ごし方についてアドバイスする際に使用してください。

    引数:
    - target_datetime: ISO 8601 形式の日時文字列
      例: 2026-04-20T18:00:00+09:00

    以下の情報を返します:
    - weather:
        - condition: 指定日時に近い時間の天気
        - temperature_c: 指定日時に近い時間の外気温
        - humidity: 指定日時に近い時間の外気湿度
        - temp_max_c: その日の最高気温
        - temp_min_c: その日の最低気温
    - season_context:
        - season: summer / winter / other
        - month: 対象日時の月
    - health_alerts:
        - heat_risk: 熱中症対策が必要か
        - dryness_risk: 乾燥対策が必要か
    """
    return get_weather_context(target_datetime=args.get("target_datetime"))

def calendar_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Google Calendar から今後の予定を取得するツールです。
    会議前の行動提案や、スケジュールに応じたアドバイスをする際に使用してください。

    以下の情報を返します:
    - has_event_within_1h: 直近1時間以内に予定があるか
    - upcoming_events: 今後の予定（開始時刻が近い順で最大3件）
    """
    return get_calendar_context()

def report_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    指定期間の室内環境データからグラフレポートを生成するツールです。
    ユーザが室内環境の推移やグラフ表示を求めた場合に使用してください。

    引数:
    - period: 取得期間 (使用できる値は "1h", "1d", "7d")

    以下の情報を返します:
    - image_url: 生成したグラフ画像の URL
    - summary: グラフ生成結果のサマリ
    - chart_data.summary_stats: CO2/温度/湿度 の 最小/最大/平均/傾向
    """
    return generate_sensor_chart_report(period=args.get("period", "1d"))

# ツールで実行する関数を辞書に登録
TOOLS: Dict[str, Dict[str, Any]] = {
    "get_weather_context_tool": {
        "description": "指定日時の天気と健康アラートを取得する。",
        "handler": weather_tool,
    },
    "get_calendar_context_tool": {
        "description": "Google Calendar から今後の予定を取得する。",
        "handler": calendar_tool,
    },
    "generate_sensor_chart_report_tool": {
        "description": "室内環境データのグラフと要約を生成する。period は '1h', '1d', '7d' のいずれか。",
        "handler": report_tool,
    },
}
