import sys
from typing import Any, Dict

from mcp.server.fastmcp import FastMCP

from common.core import (
    get_weather_context,
    get_calendar_context,
    generate_sensor_chart_report,
)

mcp = FastMCP("wellness-tools")

@mcp.tool(description="指定日時の天気と健康アラートを取得する。")
def get_weather_context_tool(target_datetime: str) -> Dict[str, Any]:
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
    return get_weather_context(target_datetime=target_datetime)

@mcp.tool(description="Google Calendar から今後の予定を取得する。")
def get_calendar_context_tool() -> Dict[str, Any]:
    """
    Google Calendar から今後の予定を取得するツールです。
    会議前の行動提案や、スケジュールに応じたアドバイスをする際に使用してください。

    以下の情報を返します:
    - has_event_within_1h: 直近1時間以内に予定があるか
    - upcoming_events: 今後の予定（開始時刻が近い順で最大3件）
    """
    return get_calendar_context()

@mcp.tool(description="室内環境データのグラフと要約を生成する。period は '1h', '1d', '7d' のいずれか。")
def generate_sensor_chart_report_tool(period: str) -> Dict[str, Any]:
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
    return generate_sensor_chart_report(period=period)

if __name__ == "__main__":
    mcp.run()
